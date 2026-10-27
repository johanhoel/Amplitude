"""Friend edition: the editor also accepts any device on the home network (RFC 1918 / link-local), still behind its password."""
import sys
p = sys.argv[1]
s = open(p).read()
a = """    def client_ok(self):
        ip = self.client_address[0]
        if ip in ALLOW:
            return True"""
b = """    def client_ok(self):
        ip = self.client_address[0]
        if ip in ALLOW:
            return True
        if os.environ.get("EDITOR_ALLOW_PRIVATE") == "1":     # friend edition: any device on the home network (password still needed)
            try:
                import ipaddress
                if ipaddress.ip_address(ip).is_private:
                    return True
            except ValueError:
                pass"""
assert s.count(a) == 1, 'client_ok changed'
s = s.replace(a, b)
a = "The editor only opens from the owner's PC."
assert s.count(a) == 1
s = s.replace(a, "The editor only opens from devices on this home network.")
open(p, 'w').write(s)
print('editor patched')
