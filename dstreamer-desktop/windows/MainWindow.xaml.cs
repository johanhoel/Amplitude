using System.Windows;
using DStreamerController.ViewModels;

namespace DStreamerController
{
    public partial class MainWindow : Window
    {
        private readonly ConnectionViewModel _vm = new();

        public MainWindow()
        {
            InitializeComponent();
            DataContext = _vm;
            // PasswordBox.Password cannot be bound, so the view model sets it through this event.
            _vm.PasswordReset += password => NewPasswordBox.Password = password;
        }

        private void NewPasswordBox_PasswordChanged(object sender, RoutedEventArgs e)
        {
            _vm.NewPassword = NewPasswordBox.Password;
        }
    }
}
