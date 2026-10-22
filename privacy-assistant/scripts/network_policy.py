"""Fixed network rules with validated local interface addresses."""
def firewall(host_addresses=()):
    import ipaddress
    addresses=sorted({str(ipaddress.IPv4Address(x)) for x in host_addresses})
    deny=('  ip daddr { '+', '.join(addresses)+' } drop\n') if addresses else ''
    return '''#!/usr/sbin/nft -f
flush ruleset
table inet privacy {
 chain output {
  type filter hook output priority 0; policy drop;
  oifname "lo" accept
HOST_DENY  ip daddr { 255.255.255.255, 10.0.2.2 } udp sport 68 udp dport 67 accept
  ip daddr { 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.168.0.0/16, 198.18.0.0/15 } drop
  meta nfproto ipv6 drop
  ip daddr { 223.5.5.5, 119.29.29.29 } udp dport 53 accept
  ip daddr { 223.5.5.5, 119.29.29.29 } tcp dport 53 accept
  tcp dport { 80, 443 } accept
 }
 chain input {
  type filter hook input priority 0; policy drop;
  iifname "lo" accept
  ct state established,related accept
  udp sport 67 udp dport 68 accept
 }
}
'''.replace('HOST_DENY',deny)
