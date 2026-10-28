using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Serialization;

namespace DanteStreamerController.Models
{
    // A saved DanteStreamer host. Port 8480 is the Virgil control panel.
    public class DanteInstance
    {
        [JsonPropertyName("id")]
        public Guid Id { get; set; } = Guid.NewGuid();

        [JsonPropertyName("name")]
        public string Name { get; set; } = "";

        [JsonPropertyName("host")]
        public string Host { get; set; } = "";

        [JsonPropertyName("port")]
        public int Port { get; set; } = 8480;

        // Virgil remote_password; empty when reached through an SSH tunnel on localhost.
        [JsonPropertyName("password")]
        public string? Password { get; set; }

        public DanteInstance() { }

        public DanteInstance(string name, string host, int port = 8480, string? password = null)
        {
            Name = name;
            Host = host;
            Port = port;
            Password = password;
        }
    }

    // GET /api/status, as built by status_json() in Virgil's src/daemon/control.cpp.
    public class DeviceStatus
    {
        [JsonPropertyName("version")]
        public string Version { get; set; } = "";

        // "running", "stopped", "restarting" or "error"
        [JsonPropertyName("status")]
        public string State { get; set; } = "";

        [JsonPropertyName("error")]
        public string Error { get; set; } = "";

        [JsonPropertyName("device")]
        public DeviceInfo Device { get; set; } = new();

        [JsonPropertyName("tx_names")]
        public string[] TxNames { get; set; } = Array.Empty<string>();

        [JsonPropertyName("rx_names")]
        public string[] RxNames { get; set; } = Array.Empty<string>();

        [JsonPropertyName("dropouts_last_hour")]
        public long DropoutsLastHour { get; set; }

        [JsonPropertyName("clock")]
        public ClockInfo Clock { get; set; } = new();

        [JsonPropertyName("clients")]
        public List<ClientInfo> Clients { get; set; } = new();

        [JsonPropertyName("meters")]
        public MeterValues Meters { get; set; } = new();

        public bool ClockLocked => Clock.State is "ptp-locked" or "ptp-master";
        public string ChannelsText => $"TX {Device.TxChannels} / RX {Device.RxChannels}";
        public string LatencyText => $"{Device.LatencyUs / 1000.0:0.#} ms";
        public string AppsText => Clients.Count == 0
            ? "none"
            : string.Join(", ", Clients.Select(c => c.Active ? c.Name + " (playing)" : c.Name));
    }

    public class DeviceInfo
    {
        [JsonPropertyName("name")]
        public string Name { get; set; } = "";

        [JsonPropertyName("interface")]
        public string Interface { get; set; } = "";

        [JsonPropertyName("address")]
        public string Address { get; set; } = "";

        [JsonPropertyName("sample_rate")]
        public int SampleRate { get; set; }

        [JsonPropertyName("tx_channels")]
        public int TxChannels { get; set; }

        [JsonPropertyName("rx_channels")]
        public int RxChannels { get; set; }

        [JsonPropertyName("latency_us")]
        public int LatencyUs { get; set; }

        [JsonPropertyName("dante")]
        public bool Dante { get; set; }

        [JsonPropertyName("enabled")]
        public bool Enabled { get; set; }
    }

    public class ClockInfo
    {
        // "stopped", "free-run", "ptp-locked" or "ptp-master"
        [JsonPropertyName("state")]
        public string State { get; set; } = "";

        [JsonPropertyName("offset_us")]
        public double OffsetUs { get; set; }

        [JsonPropertyName("grandmaster")]
        public string Grandmaster { get; set; } = "";
    }

    public class ClientInfo
    {
        [JsonPropertyName("name")]
        public string Name { get; set; } = "";

        [JsonPropertyName("active")]
        public bool Active { get; set; }
    }

    public class MeterValues
    {
        // Linear peak per channel, 0 to 1 (1 = 0 dBFS)
        [JsonPropertyName("tx")]
        public float[] Tx { get; set; } = Array.Empty<float>();

        [JsonPropertyName("rx")]
        public float[] Rx { get; set; } = Array.Empty<float>();
    }

    // One meter row in the Meters tab.
    public class MeterRow
    {
        public string Name { get; init; } = "";
        // 0 to 1 across -60..0 dBFS, the same scale as the Virgil web panel
        public double Position { get; init; }
        public string Level { get; init; } = "";

        public static List<MeterRow> Build(float[] peaks, string[] names, string prefix)
        {
            int n = Math.Max(peaks.Length, names.Length);
            return Enumerable.Range(0, n).Select(i =>
            {
                float lin = i < peaks.Length ? peaks[i] : 0;
                double db = lin > 0 ? 20 * Math.Log10(lin) : double.NegativeInfinity;
                return new MeterRow
                {
                    Name = i < names.Length && names[i] != "" ? names[i] : $"{prefix} {i + 1}",
                    Position = lin > 0 ? Math.Clamp((db + 60) / 60, 0, 1) : 0,
                    Level = lin > 0 ? $"{db:0.0} dBFS" : "silent",
                };
            }).ToList();
        }
    }
}
