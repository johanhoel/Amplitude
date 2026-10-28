using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Serialization;

namespace DanteStreamerController.Models
{
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

    public class DeviceStatus
    {
        [JsonPropertyName("device_name")]
        public string DeviceName { get; set; } = "";

        [JsonPropertyName("enabled")]
        public bool Enabled { get; set; }

        [JsonPropertyName("clock_locked")]
        public bool ClockLocked { get; set; }

        [JsonPropertyName("sample_rate")]
        public int SampleRate { get; set; }

        [JsonPropertyName("tx_channels")]
        public int TxChannels { get; set; }

        [JsonPropertyName("rx_channels")]
        public int RxChannels { get; set; }

        [JsonPropertyName("tx_meters")]
        public float[] TxMeters { get; set; } = Array.Empty<float>();

        [JsonPropertyName("rx_meters")]
        public float[] RxMeters { get; set; } = Array.Empty<float>();

        [JsonPropertyName("tx_channel_names")]
        public string[]? TxChannelNames { get; set; }

        [JsonPropertyName("rx_channel_names")]
        public string[]? RxChannelNames { get; set; }
    }

    public class ChannelMeters
    {
        public float[] TxMeters { get; set; }
        public float[] RxMeters { get; set; }
        public string[] TxNames { get; set; }
        public string[] RxNames { get; set; }

        public ChannelMeters(DeviceStatus status)
        {
            TxMeters = status.TxMeters;
            RxMeters = status.RxMeters;

            TxNames = Enumerable.Range(0, status.TxChannels)
                .Select(i => status.TxChannelNames?[i] ?? $"TX {i + 1}")
                .ToArray();

            RxNames = Enumerable.Range(0, status.RxChannels)
                .Select(i => status.RxChannelNames?[i] ?? $"RX {i + 1}")
                .ToArray();
        }
    }
}
