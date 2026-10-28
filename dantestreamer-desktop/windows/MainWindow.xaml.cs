using System.Windows;
using DanteStreamerController.ViewModels;

namespace DanteStreamerController
{
    public partial class MainWindow : Window
    {
        private readonly ConnectionViewModel _vm = new();

        public MainWindow()
        {
            InitializeComponent();
            DataContext = _vm;
            // PasswordBox.Password cannot be bound, so clear it here once the form closes.
            _vm.PropertyChanged += (_, e) =>
            {
                if (e.PropertyName == nameof(ConnectionViewModel.ShowAddForm) && !_vm.ShowAddForm)
                    NewPasswordBox.Clear();
            };
        }

        private void NewPasswordBox_PasswordChanged(object sender, RoutedEventArgs e)
        {
            _vm.NewPassword = NewPasswordBox.Password;
        }
    }
}
