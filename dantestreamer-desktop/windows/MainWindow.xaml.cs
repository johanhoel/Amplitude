using System.Windows;
using DanteStreamerController.ViewModels;

namespace DanteStreamerController
{
    public partial class MainWindow : Window
    {
        public MainWindow()
        {
            InitializeComponent();
            DataContext = new ConnectionViewModel();
        }
    }
}
