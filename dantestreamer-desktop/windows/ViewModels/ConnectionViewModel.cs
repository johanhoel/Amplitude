using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Sockets;
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
                {
                    OnPropertyChanged(nameof(IsConnecting));
                    OnInstanceSelected();
                }
            }
        }

        private DeviceStatus? _status;
        public DeviceStatus? Status
        {
            get => _status;
            set
            {
                if (!SetProperty(ref _status, value)) return;
                OnPropertyChanged(nameof(IsConnecting));
                StartCommand.NotifyCanExecuteChanged();
                StopCommand.NotifyCanExecuteChanged();
                RestartCommand.NotifyCanExecuteChanged();
                if (_waitingFor != null && value != null &&
                    (value.State == _waitingFor || DateTime.UtcNow - _actionSince > TimeSpan.FromSeconds(20)))
                {
                    ActionMessage = value.State == _waitingFor ? null : $"Virgil is {value.State}. Check its log (Virgil icon, Open log).";
                    _waitingFor = null;
                }
            }
        }

        // Start is offered only while the engine is stopped, Stop and Restart
        // only while it is not, so a click always changes something.
        private bool EngineStopped => Status?.State is "stopped" or "error";

        // Result of Start/Stop/Restart. Kept apart from Error, which every status
        // poll rewrites, and cleared once the engine reaches the new state.
        private string? _actionMessage;
        public string? ActionMessage { get => _actionMessage; set => SetProperty(ref _actionMessage, value); }
        private string? _waitingFor;   // "running", "stopped" or null
        private DateTime _actionSince;

        // A host is selected but has not answered yet.
        public bool IsConnecting => SelectedInstance != null && Status == null;

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

        // Add/edit form. _editing is the host being edited, or null when adding.
        private DanteInstance? _editing;

        private string _formTitle = "Add DanteStreamer";
        public string FormTitle { get => _formTitle; set => SetProperty(ref _formTitle, value); }

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

        // Virgil's Windows installer (DanteStreamer's Dante engine) is on its releases page.
        public const string VirgilDownloadUrl = "https://github.com/Audbol/Virgil-Virtual-Soundcard/releases";
        public const string ThisComputer = "localhost";

        public IRelayCommand UseThisComputerCommand { get; }
        public IAsyncRelayCommand InstallVirgilCommand { get; }

        private const string VirgilResource = "VirgilSetup.exe";
        // True in release builds, which carry Virgil's installer inside the exe.
        public bool VirgilBundled { get; } =
            typeof(ConnectionViewModel).Assembly.GetManifestResourceInfo(VirgilResource) != null;
        public string InstallButtonText => VirgilBundled ? "Install Virgil" : "Download Virgil";

        private string? _installMessage;
        public string? InstallMessage { get => _installMessage; set => SetProperty(ref _installMessage, value); }
        public IAsyncRelayCommand FindFromStartCommand { get; }

        public const string GuideUrl = "https://github.com/johanhoel/Amplitude/blob/main/dantestreamer-desktop/README.md#connect-to-your-dantestreamer";

        // "Find on network" results in the Add form
        public ObservableCollection<FoundHost> FoundHosts { get; } = new();

        private string? _findMessage;
        public string? FindMessage { get => _findMessage; set => SetProperty(ref _findMessage, value); }

        private FoundHost? _selectedFound;
        public FoundHost? SelectedFound
        {
            get => _selectedFound;
            set
            {
                if (!SetProperty(ref _selectedFound, value) || value == null) return;
                NewName = value.Name;
                NewHost = value.Address;
                NewPort = "8480";
            }
        }

        public IAsyncRelayCommand FindCommand { get; }
        public IRelayCommand OpenGuideCommand { get; }
        public IRelayCommand ToggleAddFormCommand { get; }
        public IRelayCommand EditSelectedCommand { get; }
        public IRelayCommand OpenPanelCommand { get; }
        public IRelayCommand SaveInstanceCommand { get; }
        public IRelayCommand RemoveInstanceCommand { get; }
        public IAsyncRelayCommand StartCommand { get; }
        public IAsyncRelayCommand StopCommand { get; }
        public IAsyncRelayCommand RestartCommand { get; }

        public ConnectionViewModel()
        {
            ToggleAddFormCommand = new RelayCommand(ToggleAddForm);
            FindCommand = new AsyncRelayCommand(FindOnNetwork);
            OpenGuideCommand = new RelayCommand(() => OpenUrl(GuideUrl));
            UseThisComputerCommand = new RelayCommand(UseThisComputer);
            InstallVirgilCommand = new AsyncRelayCommand(InstallVirgil);
            FindFromStartCommand = new AsyncRelayCommand(async () =>
            {
                if (!ShowAddForm) ToggleAddForm();
                await FindOnNetwork();
            });
            EditSelectedCommand = new RelayCommand(EditSelected);
            OpenPanelCommand = new RelayCommand(OpenPanel);
            SaveInstanceCommand = new RelayCommand(SaveNewInstance);
            RemoveInstanceCommand = new RelayCommand(RemoveSelected);
            StartCommand = new AsyncRelayCommand(() => Post("/api/start", "Starting Virgil..."), () => EngineStopped);
            StopCommand = new AsyncRelayCommand(() => Post("/api/stop", "Stopping Virgil..."), () => !EngineStopped);
            RestartCommand = new AsyncRelayCommand(() => Post("/api/restart", "Restarting the audio engine..."), () => !EngineStopped);

            _pollTimer.Tick += async (_, _) => await FetchStatus();

            LoadInstances();
            if (Instances.Count > 0)
                SelectedInstance = Instances[0];
            else
                _ = DetectThisComputer();
        }

        private void OnInstanceSelected()
        {
            Status = null;
            TxMeters = new();
            RxMeters = new();
            Error = null;
            ActionMessage = null;
            _waitingFor = null;
            _pollTimer.Stop();
            if (SelectedInstance == null) return;
            _pollTimer.Start();
            _ = FetchStatus();
        }

        private void ToggleAddForm()
        {
            if (ShowAddForm && _editing == null)
            {
                ShowAddForm = false;
                return;
            }
            _editing = null;
            FormTitle = "Add DanteStreamer";
            FoundHosts.Clear();
            FindMessage = null;
            NewName = "";
            NewHost = "localhost";
            NewPort = "8480";
            NewPassword = "";
            PasswordReset?.Invoke("");
            ShowAddForm = true;
        }

        private void EditSelected()
        {
            if (SelectedInstance == null) return;
            _editing = SelectedInstance;
            FormTitle = "Edit DanteStreamer";
            FoundHosts.Clear();
            FindMessage = null;
            NewName = _editing.Name;
            NewHost = _editing.Host;
            NewPort = _editing.Port.ToString();
            NewPassword = _editing.Password ?? "";
            PasswordReset?.Invoke(NewPassword);
            ShowAddForm = true;
        }

        // The view sets the PasswordBox, which cannot be bound.
        public event Action<string>? PasswordReset;

        // First start: if Virgil already runs on this PC, add it without asking.
        private async Task DetectThisComputer()
        {
            try
            {
                using var response = await _httpClient.GetAsync($"http://{ThisComputer}:8480/api/status");
                if (response.IsSuccessStatusCode && Instances.Count == 0) UseThisComputer();
            }
            catch { /* Virgil is not installed or not running: the start page shows the choices */ }
        }

        // Runs the bundled Virgil installer silently (/S). Windows shows one
        // permission prompt; then the app connects to Virgil on this PC.
        private async Task InstallVirgil()
        {
            using var setup = typeof(ConnectionViewModel).Assembly.GetManifestResourceStream(VirgilResource);
            if (setup == null)
            {
                OpenUrl(VirgilDownloadUrl);
                return;
            }

            var path = Path.Combine(Path.GetTempPath(), "DanteStreamer-Virgil-setup.exe");
            try
            {
                await using (var file = File.Create(path))
                    await setup.CopyToAsync(file);

                InstallMessage = "Installing Virgil. Windows asks for permission: click Yes.";
                var process = Process.Start(new ProcessStartInfo(path, "/S") { UseShellExecute = true, Verb = "runas" });
                if (process == null) throw new InvalidOperationException("the installer did not start");
                await process.WaitForExitAsync();
                if (process.ExitCode != 0)
                {
                    InstallMessage = $"Virgil setup stopped with code {process.ExitCode}. Click Install Virgil to try again.";
                    return;
                }
            }
            catch (Win32Exception)
            {
                InstallMessage = "Installation cancelled. Click Install Virgil to try again, and click Yes when Windows asks.";
                return;
            }
            catch (Exception ex)
            {
                InstallMessage = $"Could not install Virgil: {ex.Message}";
                return;
            }
            finally
            {
                try { File.Delete(path); } catch { /* still in use or already gone */ }
            }

            InstallMessage = "Virgil is installed. Connecting...";
            await Task.Delay(TimeSpan.FromSeconds(3)); // the Virgil service starts its panel
            UseThisComputer();
            InstallMessage = null;
        }

        private void UseThisComputer()
        {
            var existing = Instances.FirstOrDefault(i => i.Host is ThisComputer or "127.0.0.1");
            if (existing == null)
            {
                existing = new DanteInstance("This computer", ThisComputer);
                Instances.Add(existing);
                SaveInstances();
            }
            ShowAddForm = false;
            if (SelectedInstance == existing) OnInstanceSelected();
            else SelectedInstance = existing;
        }

        private void OpenPanel()
        {
            if (SelectedInstance != null) OpenUrl(SelectedInstance.PanelUrl);
        }

        private void OpenUrl(string url)
        {
            try
            {
                Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
            }
            catch (Exception ex)
            {
                Error = $"Cannot open the browser: {ex.Message}";
            }
        }

        private async Task FindOnNetwork()
        {
            FoundHosts.Clear();
            FindMessage = "Searching the network...";
            try
            {
                var hosts = await Discovery.FindAsync(TimeSpan.FromSeconds(3));
                foreach (var h in hosts) FoundHosts.Add(h);
                FindMessage = hosts.Count switch
                {
                    0 => "No DanteStreamer found. Check that it is switched on and on the same network, or type its IP address below.",
                    1 => "Found 1 DanteStreamer. It is filled in below.",
                    _ => $"Found {hosts.Count}. Pick one from the list.",
                };
                if (hosts.Count >= 1) SelectedFound = hosts[0];
            }
            catch (Exception ex)
            {
                FindMessage = $"Search failed: {ex.Message}. Type the IP address below.";
            }
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
            var password = NewPassword == "" ? null : NewPassword;
            var instance = _editing ?? new DanteInstance();
            instance.Name = name;
            instance.Host = host;
            instance.Port = port;
            instance.Password = password;

            if (_editing == null)
            {
                Instances.Add(instance);
            }
            else
            {
                // Replace the item so the list shows the new name and address.
                var i = Instances.IndexOf(_editing);
                Instances[i] = instance;
            }
            SaveInstances();

            _editing = null;
            NewName = "";
            NewPassword = "";
            PasswordReset?.Invoke("");
            ShowAddForm = false;
            SelectedInstance = instance;
            OnInstanceSelected();
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
            catch (HttpRequestException ex) when (ex.InnerException is SocketException { SocketErrorCode: SocketError.ConnectionRefused })
            {
                if (inst != SelectedInstance) return;
                Status = null;
                Error = RefusedHint(inst.Host, inst.Port);
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

        private async Task Post(string path, string busyText)
        {
            if (SelectedInstance == null) return;
            ActionMessage = busyText;
            try
            {
                var req = NewRequest(HttpMethod.Post, path);
                // Virgil refuses POSTs without this header (its CSRF guard).
                req.Headers.Add("X-Virgil-Request", "1");
                using var response = await _httpClient.SendAsync(req);
                if (!response.IsSuccessStatusCode)
                {
                    ActionMessage = DescribeHttpError((int)response.StatusCode, await response.Content.ReadAsStringAsync());
                    return;
                }
                _waitingFor = path == "/api/stop" ? "stopped" : "running";
                _actionSince = DateTime.UtcNow;
            }
            catch (Exception ex)
            {
                ActionMessage = $"Virgil did not answer: {ex.Message}";
                return;
            }
            await FetchStatus();
        }

        // The computer answered but nothing listens on the port. Virgil listens
        // only on 127.0.0.1 until remote access is turned on.
        private static string RefusedHint(string host, int port)
        {
            bool local = host is "localhost" or "127.0.0.1";
            return local
                ? "Virgil is not running on this computer. Click Install Virgil below, or start Virgil Control " +
                  "from the Start menu; this page connects by itself once it runs. For a DanteStreamer box on the network, add it by its IP address instead."
                : $"{host} does not accept connections on port {port}. Remote access is probably off on that DanteStreamer: " +
                  "add REMOTE_PASSWORD to its .env file and run docker compose up -d, then enter that password here. Click Setup guide for the steps.";
        }

        private static string DescribeHttpError(int code, string body)
        {
            string? message = null;
            try { message = JsonDocument.Parse(body).RootElement.GetProperty("error").GetString(); }
            catch { /* body is not Virgil's JSON error */ }
            return code switch
            {
                401 => "Wrong or missing password. Use the REMOTE_PASSWORD from DanteStreamer's .env file: select the host and click Edit.",
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
