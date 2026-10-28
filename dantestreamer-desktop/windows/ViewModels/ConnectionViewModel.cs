using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using DanteStreamerController.Models;

namespace DanteStreamerController.ViewModels
{
    public class ConnectionViewModel : ObservableObject
    {
        private readonly HttpClient _httpClient = new() { Timeout = TimeSpan.FromSeconds(3) };
        // Runs on the UI thread, so the bindings never see a background-thread update.
        private readonly DispatcherTimer _pollTimer = new() { Interval = TimeSpan.FromSeconds(1) };
        private bool _fetching;

        private static readonly string AppDataDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "DanteStreamerController");
        private static readonly string InstancesFile = Path.Combine(AppDataDir, "instances.json");

        public ObservableCollection<DanteInstance> Instances { get; } = new();

        private DanteInstance? _selectedInstance;
        public DanteInstance? SelectedInstance
        {
            get => _selectedInstance;
            set
            {
                if (SetProperty(ref _selectedInstance, value))
                    OnInstanceSelected();
            }
        }

        private DeviceStatus? _status;
        public DeviceStatus? Status
        {
            get => _status;
            set => SetProperty(ref _status, value);
        }

        private List<MeterRow> _txMeters = new();
        public List<MeterRow> TxMeters
        {
            get => _txMeters;
            set => SetProperty(ref _txMeters, value);
        }

        private List<MeterRow> _rxMeters = new();
        public List<MeterRow> RxMeters
        {
            get => _rxMeters;
            set => SetProperty(ref _rxMeters, value);
        }

        private string? _error;
        public string? Error
        {
            get => _error;
            set => SetProperty(ref _error, value);
        }

        // "Add instance" form
        private bool _showAddForm;
        public bool ShowAddForm
        {
            get => _showAddForm;
            set => SetProperty(ref _showAddForm, value);
        }

        private string _newName = "";
        public string NewName { get => _newName; set => SetProperty(ref _newName, value); }

        private string _newHost = "localhost";
        public string NewHost { get => _newHost; set => SetProperty(ref _newHost, value); }

        private string _newPort = "8480";
        public string NewPort { get => _newPort; set => SetProperty(ref _newPort, value); }

        private string _newPassword = "";
        public string NewPassword { get => _newPassword; set => SetProperty(ref _newPassword, value); }

        public IRelayCommand ToggleAddFormCommand { get; }
        public IRelayCommand SaveInstanceCommand { get; }
        public IRelayCommand RemoveInstanceCommand { get; }
        public IAsyncRelayCommand StartCommand { get; }
        public IAsyncRelayCommand StopCommand { get; }
        public IAsyncRelayCommand RestartCommand { get; }

        public ConnectionViewModel()
        {
            ToggleAddFormCommand = new RelayCommand(() => ShowAddForm = !ShowAddForm);
            SaveInstanceCommand = new RelayCommand(SaveNewInstance);
            RemoveInstanceCommand = new RelayCommand(RemoveSelected);
            StartCommand = new AsyncRelayCommand(() => Post("/api/start"));
            StopCommand = new AsyncRelayCommand(() => Post("/api/stop"));
            RestartCommand = new AsyncRelayCommand(() => Post("/api/restart"));

            _pollTimer.Tick += async (_, _) => await FetchStatus();

            LoadInstances();
            if (Instances.Count == 0)
                ShowAddForm = true;
            else
                SelectedInstance = Instances[0];
        }

        private void OnInstanceSelected()
        {
            Status = null;
            TxMeters = new();
            RxMeters = new();
            Error = null;
            _pollTimer.Stop();
            if (SelectedInstance == null) return;
            _pollTimer.Start();
            _ = FetchStatus();
        }

        private void SaveNewInstance()
        {
            var host = NewHost.Trim();
            if (host == "")
            {
                Error = "Enter a host name or IP address.";
                return;
            }
            if (!int.TryParse(NewPort, out var port) || port < 1 || port > 65535)
            {
                Error = "The port must be a number from 1 to 65535.";
                return;
            }

            var name = NewName.Trim() == "" ? host : NewName.Trim();
            var instance = new DanteInstance(name, host, port, NewPassword == "" ? null : NewPassword);
            Instances.Add(instance);
            SaveInstances();

            NewName = "";
            NewPassword = "";
            ShowAddForm = false;
            SelectedInstance = instance;
        }

        private void RemoveSelected()
        {
            if (SelectedInstance == null) return;
            Instances.Remove(SelectedInstance);
            SelectedInstance = null;
            SaveInstances();
        }

        private HttpRequestMessage NewRequest(HttpMethod method, string path)
        {
            var inst = SelectedInstance!;
            var req = new HttpRequestMessage(method, $"http://{inst.Host}:{inst.Port}{path}");
            // Virgil asks other computers for remote_password with HTTP Basic auth (any user name).
            if (!string.IsNullOrEmpty(inst.Password))
            {
                var token = Convert.ToBase64String(Encoding.UTF8.GetBytes("app:" + inst.Password));
                req.Headers.Authorization = new AuthenticationHeaderValue("Basic", token);
            }
            return req;
        }

        private async Task FetchStatus()
        {
            if (SelectedInstance == null || _fetching) return;
            var inst = SelectedInstance;
            _fetching = true;
            try
            {
                using var response = await _httpClient.SendAsync(NewRequest(HttpMethod.Get, "/api/status"));
                var json = await response.Content.ReadAsStringAsync();
                if (inst != SelectedInstance) return;

                if (!response.IsSuccessStatusCode)
                {
                    Status = null;
                    Error = DescribeHttpError((int)response.StatusCode, json);
                    return;
                }

                var status = JsonSerializer.Deserialize<DeviceStatus>(json);
                if (status == null) return;
                Status = status;
                TxMeters = MeterRow.Build(status.Meters.Tx, status.TxNames, "TX");
                RxMeters = MeterRow.Build(status.Meters.Rx, status.RxNames, "RX");
                Error = status.Error == "" ? null : status.Error;
            }
            catch (Exception ex)
            {
                if (inst != SelectedInstance) return;
                Status = null;
                Error = $"Cannot reach {inst.Host}:{inst.Port} ({ex.Message})";
            }
            finally
            {
                _fetching = false;
            }
        }

        private async Task Post(string path)
        {
            if (SelectedInstance == null) return;
            try
            {
                var req = NewRequest(HttpMethod.Post, path);
                // Virgil refuses POSTs without this header (its CSRF guard).
                req.Headers.Add("X-Virgil-Request", "1");
                using var response = await _httpClient.SendAsync(req);
                if (!response.IsSuccessStatusCode)
                    Error = DescribeHttpError((int)response.StatusCode, await response.Content.ReadAsStringAsync());
            }
            catch (Exception ex)
            {
                Error = ex.Message;
            }
            await FetchStatus();
        }

        private static string DescribeHttpError(int code, string body)
        {
            string? message = null;
            try { message = JsonDocument.Parse(body).RootElement.GetProperty("error").GetString(); }
            catch { /* body is not Virgil's JSON error */ }
            return code switch
            {
                401 => "Wrong or missing password (Virgil remote_password).",
                403 => message ?? "Refused. Turn on remote access in Virgil, or use an SSH tunnel to localhost.",
                429 => "Too many wrong passwords. Wait a minute and try again.",
                _ => $"HTTP {code}: {message ?? body}",
            };
        }

        private void LoadInstances()
        {
            try
            {
                if (!File.Exists(InstancesFile)) return;
                var instances = JsonSerializer.Deserialize<List<DanteInstance>>(File.ReadAllText(InstancesFile)) ?? new();
                foreach (var instance in instances)
                    Instances.Add(instance);
            }
            catch { /* Ignore load errors */ }
        }

        private void SaveInstances()
        {
            try
            {
                Directory.CreateDirectory(AppDataDir);
                var json = JsonSerializer.Serialize(Instances, new JsonSerializerOptions { WriteIndented = true });
                File.WriteAllText(InstancesFile, json);
            }
            catch { /* Ignore save errors */ }
        }
    }
}
