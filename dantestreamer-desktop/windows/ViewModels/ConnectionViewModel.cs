using System;
using System.Collections.ObjectModel;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Input;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using DanteStreamerController.Models;

namespace DanteStreamerController.ViewModels
{
    public class ConnectionViewModel : ObservableObject
    {
        private readonly HttpClient _httpClient = new();
        private CancellationTokenSource? _pollingCts;

        private ObservableCollection<DanteInstance> _instances = new();
        public ObservableCollection<DanteInstance> Instances
        {
            get => _instances;
            set => SetProperty(ref _instances, value);
        }

        private DanteInstance? _selectedInstance;
        public DanteInstance? SelectedInstance
        {
            get => _selectedInstance;
            set
            {
                if (SetProperty(ref _selectedInstance, value))
                {
                    OnInstanceSelected();
                }
            }
        }

        private DeviceStatus? _status;
        public DeviceStatus? Status
        {
            get => _status;
            set => SetProperty(ref _status, value);
        }

        private ChannelMeters? _meters;
        public ChannelMeters? Meters
        {
            get => _meters;
            set => SetProperty(ref _meters, value);
        }

        private bool _isConnected;
        public bool IsConnected
        {
            get => _isConnected;
            set => SetProperty(ref _isConnected, value);
        }

        private string? _error;
        public string? Error
        {
            get => _error;
            set => SetProperty(ref _error, value);
        }

        public IAsyncRelayCommand<DanteInstance> ConnectCommand { get; }
        public IRelayCommand DisconnectCommand { get; }
        public IRelayCommand<DanteInstance> RemoveInstanceCommand { get; }

        public ConnectionViewModel()
        {
            ConnectCommand = new AsyncRelayCommand<DanteInstance>(Connect);
            DisconnectCommand = new RelayCommand(Disconnect);
            RemoveInstanceCommand = new RelayCommand<DanteInstance>(RemoveInstance);

            LoadInstances();

            _httpClient.Timeout = TimeSpan.FromSeconds(5);
        }

        private async Task Connect(DanteInstance? instance)
        {
            if (instance == null) return;

            SelectedInstance = instance;
            IsConnected = true;
            Error = null;

            await StartPolling();
        }

        private void Disconnect()
        {
            _pollingCts?.Cancel();
            _pollingCts?.Dispose();
            _pollingCts = null;

            SelectedInstance = null;
            IsConnected = false;
            Status = null;
            Meters = null;
        }

        private void RemoveInstance(DanteInstance? instance)
        {
            if (instance == null) return;

            Instances.Remove(instance);

            if (SelectedInstance?.Id == instance.Id)
            {
                Disconnect();
            }

            SaveInstances();
        }

        private async void OnInstanceSelected()
        {
            if (SelectedInstance != null && IsConnected)
            {
                await StartPolling();
            }
        }

        private async Task StartPolling()
        {
            _pollingCts?.Cancel();
            _pollingCts = new CancellationTokenSource();

            _ = Task.Run(async () =>
            {
                while (!_pollingCts.Token.IsCancellationRequested)
                {
                    try
                    {
                        await FetchStatus();
                        await Task.Delay(2000, _pollingCts.Token);
                    }
                    catch (OperationCanceledException)
                    {
                        break;
                    }
                }
            });
        }

        private async Task FetchStatus()
        {
            if (SelectedInstance == null) return;

            try
            {
                var url = $"http://{SelectedInstance.Host}:{SelectedInstance.Port}/api/status";
                var response = await _httpClient.GetAsync(url);

                if (response.IsSuccessStatusCode)
                {
                    var json = await response.Content.ReadAsStringAsync();
                    var options = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
                    Status = JsonSerializer.Deserialize<DeviceStatus>(json, options);

                    if (Status != null)
                    {
                        Meters = new ChannelMeters(Status);
                    }

                    Error = null;
                }
                else
                {
                    Error = $"HTTP {response.StatusCode}";
                }
            }
            catch (Exception ex)
            {
                Error = $"Error: {ex.Message}";
            }
        }

        public void AddInstance(DanteInstance instance)
        {
            if (!Instances.Any(x => x.Id == instance.Id))
            {
                Instances.Add(instance);
                SaveInstances();
            }
        }

        private void LoadInstances()
        {
            try
            {
                var appDataPath = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                    "DanteStreamerController",
                    "instances.json"
                );

                if (File.Exists(appDataPath))
                {
                    var json = File.ReadAllText(appDataPath);
                    var instances = JsonSerializer.Deserialize<List<DanteInstance>>(json) ?? new();

                    foreach (var instance in instances)
                    {
                        Instances.Add(instance);
                    }
                }
            }
            catch { /* Ignore load errors */ }
        }

        private void SaveInstances()
        {
            try
            {
                var appDataPath = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                    "DanteStreamerController"
                );

                Directory.CreateDirectory(appDataPath);

                var filePath = Path.Combine(appDataPath, "instances.json");
                var json = JsonSerializer.Serialize(Instances, new JsonSerializerOptions { WriteIndented = true });
                File.WriteAllText(filePath, json);
            }
            catch { /* Ignore save errors */ }
        }
    }
}
