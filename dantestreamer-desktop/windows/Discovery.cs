using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading.Tasks;

namespace DanteStreamerController
{
    // A DanteStreamer found on the network.
    public record FoundHost(string Name, string Address)
    {
        public override string ToString() => $"{Name} ({Address})";
    }

    // Finds DanteStreamer hosts by their AirPlay receiver: one mDNS question for
    // _raop._tcp.local, sent from an ordinary UDP port. Responders then answer by
    // unicast to that port (RFC 6762 section 6.7), so no multicast group join and
    // no firewall rule is needed. DanteStreamer's receiver is Shairport Sync, which
    // says so in its TXT record (am=ShairportSync); Apple TVs and HomePods do not.
    public static class Discovery
    {
        public static async Task<List<FoundHost>> FindAsync(TimeSpan wait)
        {
            var found = new Dictionary<string, FoundHost>();
            using var udp = new UdpClient(new IPEndPoint(IPAddress.Any, 0));
            byte[] query = BuildQuery("_raop._tcp.local");
            await udp.SendAsync(query, query.Length, new IPEndPoint(IPAddress.Parse("224.0.0.251"), 5353));

            var deadline = DateTime.UtcNow + wait;
            while (DateTime.UtcNow < deadline)
            {
                var receive = udp.ReceiveAsync();
                var done = await Task.WhenAny(receive, Task.Delay(deadline - DateTime.UtcNow));
                if (done != receive) break;
                var result = receive.Result;
                if (result.RemoteEndPoint.AddressFamily != AddressFamily.InterNetwork) continue;
                try
                {
                    var host = Parse(result.Buffer, result.RemoteEndPoint.Address.ToString());
                    if (host != null) found[host.Address] = host;
                }
                catch (IndexOutOfRangeException) { /* malformed packet */ }
                catch (ArgumentException) { /* malformed packet */ }
            }
            return found.Values.OrderBy(h => h.Name).ToList();
        }

        private static byte[] BuildQuery(string name)
        {
            var q = new List<byte> { 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0 }; // id 0, 1 question
            foreach (var label in name.Split('.'))
            {
                q.Add((byte)label.Length);
                q.AddRange(Encoding.ASCII.GetBytes(label));
            }
            q.AddRange(new byte[] { 0, 0, 12, 0, 1 }); // end of name, type PTR, class IN
            return q.ToArray();
        }

        private static FoundHost? Parse(byte[] d, string sender)
        {
            if (!Encoding.Latin1.GetString(d).Contains("ShairportSync")) return null;

            int questions = (d[4] << 8) | d[5];
            int records = ((d[6] << 8) | d[7]) + ((d[8] << 8) | d[9]) + ((d[10] << 8) | d[11]);
            int o = 12;
            for (int i = 0; i < questions; i++) { ReadName(d, ref o); o += 4; }
            for (int i = 0; i < records; i++)
            {
                ReadName(d, ref o);
                int type = (d[o] << 8) | d[o + 1];
                int length = (d[o + 8] << 8) | d[o + 9];
                o += 10;
                if (type == 12)
                {
                    int p = o;
                    // "A84985A16ECB@DanteStreamer._raop._tcp.local" -> "DanteStreamer"
                    string instance = ReadName(d, ref p).Split("._raop.")[0];
                    int at = instance.IndexOf('@');
                    return new FoundHost(at >= 0 ? instance[(at + 1)..] : instance, sender);
                }
                o += length;
            }
            return null;
        }

        // DNS name with compression pointers.
        private static string ReadName(byte[] d, ref int o)
        {
            var labels = new List<string>();
            int pos = o, end = -1, jumps = 0;
            while (true)
            {
                int len = d[pos];
                if (len == 0) { pos++; break; }
                if ((len & 0xC0) == 0xC0)
                {
                    if (end < 0) end = pos + 2;
                    if (++jumps > 20) throw new ArgumentException("pointer loop");
                    pos = ((len & 0x3F) << 8) | d[pos + 1];
                    continue;
                }
                labels.Add(Encoding.UTF8.GetString(d, pos + 1, len));
                pos += 1 + len;
            }
            o = end >= 0 ? end : pos;
            return string.Join(".", labels);
        }
    }
}
