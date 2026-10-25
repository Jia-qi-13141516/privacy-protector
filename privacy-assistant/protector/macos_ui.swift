// A root-owned, root-run local window. It never sends material to the public API.
import AppKit
import Foundation
import UniformTypeIdentifiers
import Darwin

guard geteuid() == 0, CommandLine.arguments.count == 4 else { exit(2) }
let mode = CommandLine.arguments[1]
let job = CommandLine.arguments[2]
let socketPath = CommandLine.arguments[3]
guard job.range(of: "^[a-f0-9]{32}$", options: .regularExpression) != nil else { exit(2) }

func rpc(_ value: [String:Any]) throws -> [String:Any] {
    var st = stat()
    guard lstat(socketPath, &st) == 0, st.st_uid == 0, st.st_mode & S_IFMT == S_IFSOCK else { throw NSError(domain:"Unavailable",code:1) }
    let fd = socket(AF_UNIX, SOCK_STREAM, 0)
    guard fd >= 0 else { throw NSError(domain:"Unavailable",code:1) }
    defer { close(fd) }
    var address = sockaddr_un(); address.sun_family = sa_family_t(AF_UNIX)
    let bytes = Array(socketPath.utf8CString)
    guard bytes.count <= MemoryLayout.size(ofValue: address.sun_path) else { throw NSError(domain:"Path",code:1) }
    withUnsafeMutableBytes(of: &address.sun_path) { target in bytes.withUnsafeBytes { target.copyBytes(from:$0) } }
    let connected = withUnsafePointer(to:&address) { ptr in ptr.withMemoryRebound(to:sockaddr.self,capacity:1) { connect(fd,$0,socklen_t(MemoryLayout<sockaddr_un>.size)) } }
    guard connected == 0 else { throw NSError(domain:"Unavailable",code:1) }
    var uid:uid_t = 99;var gid:gid_t = 99
    guard getpeereid(fd,&uid,&gid) == 0,uid == 0 else { throw NSError(domain:"Untrusted",code:1) }
    var timeout = timeval(tv_sec:120,tv_usec:0)
    setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&timeout,socklen_t(MemoryLayout<timeval>.size))
    var data = try JSONSerialization.data(withJSONObject:value);data.append(10)
    guard data.count <= 8192 else { throw NSError(domain:"Request",code:1) }
    try data.withUnsafeBytes { raw in
        var offset=0
        while offset < data.count {
            let sent=write(fd,raw.baseAddress!.advanced(by:offset),data.count-offset)
            guard sent>0 else { throw NSError(domain:"Write",code:1) };offset+=sent
        }
    }
    var received=Data();var buffer=[UInt8](repeating:0,count:4096)
    while !received.contains(10) {
        let count=read(fd,&buffer,buffer.count)
        guard count>0,received.count+count<=500000 else { throw NSError(domain:"Response",code:1) }
        received.append(buffer,count:count)
    }
    return try JSONSerialization.jsonObject(with:received) as! [String:Any]
}
func alert(_ text:String,_ detail:String="") {
    let a=NSAlert();a.messageText=text;a.informativeText=detail;a.addButton(withTitle:"关闭");a.runModal()
}
func recoverOriginal(_ ext:String) throws {
    let confirm=NSAlert();confirm.messageText="取回原件？"
    confirm.informativeText="取回后，普通软件和 Agent 也可能读取原件。继续保护则不改变权限。"
    confirm.addButton(withTitle:"继续保护");confirm.addButton(withTitle:"取回原件")
    guard confirm.runModal() == .alertSecondButtonReturn else { return }
    let restored=try rpc(["action":"restore","id":job])
    if restored["error"] == nil { alert("原件已恢复普通访问");return }
    guard [".xlsx",".csv",".txt",".md",".docx",".pdf"].contains(ext) else {
        alert("无法恢复原件","没有可用的受保护快照，未改变文件权限。");return
    }
    let save=NSSavePanel();save.title="取回原件副本";save.nameFieldStringValue="取回的原件"+ext
    save.message="原位置无法恢复。将尝试保存经过完整性核验的原件副本；保护区中的文件保留。"
    save.allowedContentTypes=[UTType(filenameExtension:String(ext.dropFirst()))].compactMap { $0 }
    if save.runModal() == .OK,let url=save.url {
        let recovered=try rpc(["action":"recover","id":job,"destination":url.path])
        if recovered["recovered"] as? Bool == true { alert("原件副本已保存") }
        else { alert("原件副本未保存","恢复检查未通过；已有文件不会被覆盖，保护区中的文件没有删除。") }
    }
}
let app=NSApplication.shared
app.setActivationPolicy(.regular);app.activate(ignoringOtherApps:true)
do {
    if mode == "select" {
        let panel=NSOpenPanel();panel.title="Privacy Protector";panel.prompt="选择并保护"
        panel.message="选入后，原件由本地保护组件保管，普通 Agent 无法直接读取。确认结果后可导出结果文件。"
        panel.canChooseDirectories=false;panel.allowsMultipleSelection=false
        panel.allowedContentTypes=["xlsx","csv","txt","md","docx","pdf"].compactMap { UTType(filenameExtension:$0) }
        if panel.runModal() == .OK, let url=panel.url {
            let result=try rpc(["action":"select","id":job,"path":url.path])
            if result["phase"] as? String == "blocked" || result["error"] != nil {
                alert("文件未进入处理流程", "保护检查未通过；原件可能仍受保护。请在受保护窗口中取回，不能交给聊天窗口绕过处理。")
            }
        } else { _ = try rpc(["action":"cancel","id":job]) }
    } else if mode == "review" {
        let result=try rpc(["action":"review","id":job])
        guard let preview=result["preview"] as? String,let ext=result["extension"] as? String else {
            let a=NSAlert();a.messageText="任务未完成";a.informativeText="没有通过保护与处理检查，原件不会自动解锁。";a.addButton(withTitle:"关闭");a.addButton(withTitle:"取回原件")
            if a.runModal() == .alertSecondButtonReturn {
                try recoverOriginal(result["source_extension"] as? String ?? "")
            }
            exit(0)
        }
        let a=NSAlert();a.messageText="核对处理结果";a.informativeText=result["notice"] as? String ?? "原件继续受保护。"
        let scroll=NSScrollView(frame:NSRect(x:0,y:0,width:760,height:450));scroll.hasVerticalScroller=true
        let text=NSTextView(frame:scroll.bounds);text.string=preview;text.isEditable=false;text.isSelectable=false;text.font=NSFont.monospacedSystemFont(ofSize:13,weight:.regular)
        scroll.documentView=text;a.accessoryView=scroll
        a.addButton(withTitle:"确认并保存结果");a.addButton(withTitle:"暂不导出");a.addButton(withTitle:"取回原件")
        let choice=a.runModal()
        if choice == .alertThirdButtonReturn {
            if result["phase"] as? String == "waiting_for_confirmation" { _=try rpc(["action":"cancel","id":job]) }
            try recoverOriginal(result["source_extension"] as? String ?? "")
        } else if choice == .alertFirstButtonReturn {
            let save=NSSavePanel();save.title="保存确认后的结果";save.nameFieldStringValue="处理结果"+ext
            save.message="导出的结果是普通文件，可被其他软件读取；受保护原件不会解锁。"
            save.allowedContentTypes=[UTType(filenameExtension:String(ext.dropFirst()))].compactMap { $0 }
            if save.runModal() == .OK,let url=save.url {
                let r=try rpc(["action":"confirm","id":job,"destination":url.path])
                if r["phase"] as? String == "confirmed" { alert("结果已保存", "原件继续保留在保护范围内。") }
                else { alert("结果未保存","请选择属于当前用户的本地目录和一个不存在的文件名。") }
            }
        }
    }
} catch { alert("本地保护组件未就绪","已停止处理，没有上传或解锁原件。") }
