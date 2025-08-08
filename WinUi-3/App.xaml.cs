using kktix.Models;
using Microsoft.UI;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Navigation;
using Microsoft.UI.Xaml.Shapes;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.WindowsRuntime;
using System.Text;
using System.Text.Json;
using Windows.ApplicationModel;
using System.Threading.Tasks;
using Windows.ApplicationModel.Activation;
using Windows.Foundation;
using Windows.Foundation.Collections;
using Windows.Graphics;
using WinRT;
using WinRT.Interop;



namespace kktix
{
    /// <summary>
    /// Provides application-specific behavior to supplement the default Application class.
    /// </summary>
    public partial class App : Application
    {
        private Window? _window;

        /// <summary>
        /// Initializes the singleton application object.  This is the first line of authored code
        /// executed, and as such is the logical equivalent of main() or WinMain().
        /// </summary>
        public App()
        {
            InitializeComponent();

            // 初始設定檔
            LoadUserConfig();

            // 全域例外處理，避免未處理的例外彈出 Win32 偵錯對話框
            this.UnhandledException += App_UnhandledException;
            AppDomain.CurrentDomain.UnhandledException += CurrentDomain_UnhandledException;
            TaskScheduler.UnobservedTaskException += TaskScheduler_UnobservedTaskException;

            // 抑制系統 GP Fault 對話框（避免 Debug 模式彈 JIT 對話框）
            const uint SEM_FAILCRITICALERRORS = 0x0001;
            const uint SEM_NOGPFAULTERRORBOX = 0x0002;
            const uint SEM_NOALIGNMENTFAULTEXCEPT = 0x0004;
            NativeMethods.SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOALIGNMENTFAULTEXCEPT);
        }

        /// <summary> 如果設定檔初始化失敗，則為 true </summary>
        public static bool IsConfigInitializeFailed { get; private set; } = false;
        public static string? ConfigErrorMessage { get; private set; }

        /// <summary>
        /// Invoked when the application is launched.
        /// </summary>
        /// <param name="args">Details about the launch request and process.</param>
        internal static partial class NativeMethods
        {
            [LibraryImport("user32.dll", EntryPoint = "GetWindowLongPtrW", SetLastError = true)]
            internal static partial nint GetWindowLongPtr(IntPtr hWnd, int nIndex);

            [LibraryImport("user32.dll", EntryPoint = "SetWindowLongPtrW", SetLastError = true)]
            internal static partial nint SetWindowLongPtr(IntPtr hWnd, int nIndex, nint dwNewLong);

            [LibraryImport("kernel32.dll", EntryPoint = "SetErrorMode")]
            internal static partial uint SetErrorMode(uint uMode);
        }

        private const int GWL_STYLE = -16;
        private const int WS_MAXIMIZEBOX = 0x00010000;
        private const int WS_THICKFRAME = 0x00040000;
        protected override void OnLaunched(Microsoft.UI.Xaml.LaunchActivatedEventArgs args)
        {
            _window = new MainWindow();
            _window.Activate();

            // 設定視窗大小與位置
            IntPtr hWnd = WindowNative.GetWindowHandle(_window);
            var windowId = Win32Interop.GetWindowIdFromWindow(hWnd);
            var mainAppWindow = AppWindow.GetFromWindowId(windowId);

            mainAppWindow.Resize(new SizeInt32(640, 720));
            var displayArea = DisplayArea.GetFromWindowId(windowId, DisplayAreaFallback.Primary);
            var centerX = displayArea.WorkArea.Width / 2 - 640 / 2;
            var centerY = displayArea.WorkArea.Height / 2 - 720 / 2;
            mainAppWindow.Move(new PointInt32(centerX, centerY));

            // 設定視窗圖示（Alt+Tab/標題列/工作列）
            try
            {
                var iconPath = System.IO.Path.Combine(AppContext.BaseDirectory, "Assets", "AppIcon.ico");
                if (File.Exists(iconPath))
                {
                    mainAppWindow.SetIcon(iconPath);
                }
            }
            catch { }

            // 移除最大化按鈕 & 禁止拉伸
            nint style = NativeMethods.GetWindowLongPtr(hWnd, GWL_STYLE);
            style &= ~WS_MAXIMIZEBOX;   // 移除最大化按鈕
            style &= ~WS_THICKFRAME;    // 移除可調整邊框
            nint result = NativeMethods.SetWindowLongPtr(hWnd, GWL_STYLE, style);
            if (result == 0 && _window?.Content is FrameworkElement fe)
            {
                // 顯示給使用者
                var dialog = new ContentDialog
                {
                    Title = "視窗設定失敗",
                    Content = "無法正確鎖定視窗大小，請重新啟動或聯絡支援。",
                    CloseButtonText = "確定",
                    XamlRoot = fe.XamlRoot
                };
                _ = dialog.ShowAsync();
            }

            // 保留最小化按鈕 & 關閉按鈕
            var presenter = mainAppWindow.Presenter as OverlappedPresenter;
            if (presenter != null)
            {
                presenter.IsMinimizable = true;
            }
        }

        private static void App_UnhandledException(object sender, Microsoft.UI.Xaml.UnhandledExceptionEventArgs e)
        {
            try
            {
                LogException(e.Exception);
            }
            catch { }
            e.Handled = true;
        }

        private static void CurrentDomain_UnhandledException(object? sender, System.UnhandledExceptionEventArgs e)
        {
            try
            {
                if (e.ExceptionObject is Exception ex)
                {
                    LogException(ex);
                }
            }
            catch { }
        }

        private static void TaskScheduler_UnobservedTaskException(object? sender, System.Threading.Tasks.UnobservedTaskExceptionEventArgs e)
        {
            try
            {
                LogException(e.Exception);
                e.SetObserved();
            }
            catch { }
        }

        private static void LogException(Exception ex)
        {
            try
            {
                string logFolder = System.IO.Path.Combine(AppContext.BaseDirectory, "Logs");
                Directory.CreateDirectory(logFolder);
                string logPath = System.IO.Path.Combine(logFolder, "unhandled.txt");
                File.AppendAllText(logPath, $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {ex}\n");
            }
            catch { }
        }

        private static readonly JsonSerializerOptions _jsonOptions = new()
        {
            WriteIndented = true
        };

        /// <summary>
        /// 讀取 UserConfig.json 設定檔
        /// </summary>
        private static void LoadUserConfig()
        {
            try
            {
                string exePath = System.IO.Path.Combine(AppContext.BaseDirectory, "UserConfig.json");
                string localDir = System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "kktix");
                string localPath = System.IO.Path.Combine(localDir, "UserConfig.json");
                var utf8NoBom = new UTF8Encoding(false);

                UserConfig config;

                string? loadPath = null;
                if (File.Exists(exePath))
                {
                    loadPath = exePath;
                }
                else if (File.Exists(localPath))
                {
                    loadPath = localPath;
                }

                if (loadPath != null)
                {
                    string jsonString = File.ReadAllText(loadPath, utf8NoBom);
                    var deserialized = JsonSerializer.Deserialize<UserConfig>(jsonString);
                    config = deserialized ?? new UserConfig();
                }
                else
                {
                    config = new UserConfig();
                    SaveConfig(config);
                }

                // 指派給全域 Instance
                UserConfig.Load(config);
            }
            catch (Exception ex)
            {
                string logFolder = System.IO.Path.Combine(AppContext.BaseDirectory, "Logs");
                Directory.CreateDirectory(logFolder);
                string logPath = System.IO.Path.Combine(logFolder, "error.txt");
                File.AppendAllText(logPath, $"[{DateTime.Now}] LoadConfig error: {ex}\n");
                IsConfigInitializeFailed = true;
                ConfigErrorMessage = $"設定檔載入失敗，請將以下檔案回報給開發者：\n{logPath}"; 
            }
        }

        /// <summary>
        /// 儲存 UserConfig.json 設定檔
        /// 第二個參數 fromUI 用來判斷是否從 UI 儲存，若為 true: fromUI，若為 false: 初始化時呼叫
        /// </summary>
        private static void SaveConfig(UserConfig config)
        {
            try
            {
                string exePath = System.IO.Path.Combine(AppContext.BaseDirectory, "UserConfig.json");
                string localDir = System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "kktix");
                string localPath = System.IO.Path.Combine(localDir, "UserConfig.json");
                var utf8NoBom = new UTF8Encoding(false);

                string jsonString = JsonSerializer.Serialize(config, _jsonOptions);

                try
                {
                    File.WriteAllText(exePath, jsonString, utf8NoBom);
                }
                catch
                {
                    Directory.CreateDirectory(localDir);
                    File.WriteAllText(localPath, jsonString, utf8NoBom);
                }
            }
            catch (Exception ex)
            {
                string logFolder = System.IO.Path.Combine(AppContext.BaseDirectory, "Logs");
                Directory.CreateDirectory(logFolder);
                string logPath = System.IO.Path.Combine(logFolder, "error.txt");
                File.AppendAllText(logPath, $"[{DateTime.Now}] LoadConfig error: {ex}\n");

                IsConfigInitializeFailed = true;
                ConfigErrorMessage =
                    $"此程式初始化時發生錯誤。\n\n請將以下錯誤記錄回報給開發者：\n{logPath}";
            }
        }
    }
}
