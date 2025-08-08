using kktix.Models;
using Microsoft.UI;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Navigation;
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices.WindowsRuntime;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using System.Text.RegularExpressions;
using System.Diagnostics;
using Windows.Foundation;
using Windows.Foundation.Collections;
using Windows.UI;


namespace kktix
{
    /// <summary>
    /// An empty window that can be used on its own or navigated to within a Frame.
    /// </summary>
    public sealed partial class MainWindow : Window
    {
        private bool _isClosed;
        [System.Text.RegularExpressions.GeneratedRegex("^\\d+$")]
        private static partial System.Text.RegularExpressions.Regex DigitsRegex();
        public MainWindow()
        {
            InitializeComponent();

            this.ExtendsContentIntoTitleBar = true;
            this.SetTitleBar(CustomTitleBar);
            this.Closed += (_, __) => _isClosed = true;
            var hwnd = WinRT.Interop.WindowNative.GetWindowHandle(this);
            var windowId = Microsoft.UI.Win32Interop.GetWindowIdFromWindow(hwnd);
            var mainAppWindow = Microsoft.UI.Windowing.AppWindow.GetFromWindowId(windowId);

            var titleBar = mainAppWindow.TitleBar;
            titleBar.BackgroundColor = Microsoft.UI.Colors.Transparent;
            titleBar.ButtonBackgroundColor = Microsoft.UI.Colors.Transparent;
            titleBar.ButtonInactiveBackgroundColor = Microsoft.UI.Colors.Transparent;
            titleBar.InactiveBackgroundColor = Microsoft.UI.Colors.Transparent;
        }
        private async void RootGrid_Loaded(object sender, RoutedEventArgs e)
        {
            // 避免重複觸發，解除 Loaded 事件
            RootGrid.Loaded -= RootGrid_Loaded;

            if (App.IsConfigInitializeFailed && !string.IsNullOrEmpty(App.ConfigErrorMessage))
            {
                var dialog = new ContentDialog
                {
                    Title = "發生錯誤",
                    Content = App.ConfigErrorMessage,
                    PrimaryButtonText = "確定",
                    DefaultButton = ContentDialogButton.Primary,
                    XamlRoot = RootGrid.XamlRoot
                };
                await dialog.ShowAsync();
                Close();
            }
            else
            {
                LoadUserConfigToUI();
            }
        }

        private void LoadUserConfigToUI()
        {
            var config = UserConfig.Instance;
            NameTextBox.Text = config.Username;
            PasswordTextBox.Password = config.Password;
            TicketName1TextBox.Text = config.TicketName1;
            TicketName2TextBox.Text = config.TicketName2;
            PriceTextBox.Text = config.TicketPrice;
            QuantityTextBox.Text = config.TicketQuantity.ToString();
            TargetUrlTextBox.Text = config.TicketUrl;
            SeatAutoRadioButton.IsChecked = UserConfig.Instance.IsAutoAllocation;
            SeatManualRadioButton.IsChecked = !UserConfig.Instance.IsAutoAllocation;
            PaymentAutoRadioButton.IsChecked = UserConfig.Instance.IsAutoPayment;
            PaymentManualRadioButton.IsChecked = !UserConfig.Instance.IsAutoPayment;

            selectedDateTime = config.SaleTime;
            var culture = new CultureInfo("zh-TW");
            DatePickerButton.Content = selectedDateTime.ToString("yyyy/MM/dd", culture);
            TimePickerButton.Content = selectedDateTime.ToString("tt hh:mm:ss", culture);
            int hour12 = selectedDateTime.Hour % 12;
            if (hour12 == 0) hour12 = 12;
            HourBox.Text = hour12.ToString();
            MinuteBox.Text = selectedDateTime.Minute.ToString("D2");
            SecondBox.Text = selectedDateTime.Second.ToString("D2");
            AmPmToggle.IsOn = selectedDateTime.Hour < 12;
        }

        private async void Save_Click(object sender, RoutedEventArgs e)
        {
            // TODO: ���Ҹ�ƫ�~�x�s
            SaveUIToConfig();
            await SaveConfigWithDialogAsync();
        }

        private async void Start_Click(object sender, RoutedEventArgs e)
        {
            if (_isClosed) return;

            // 1) 驗證輸入
            var errors = ValidateInputs();
            if (errors.Length > 0)
            {
                ContentDialog errDlg = new()
                {
                    Title = "輸入資料有誤",
                    Content = errors.ToString(),
                    CloseButtonText = "確定",
                    XamlRoot = (this.Content as FrameworkElement)?.XamlRoot
                };
                try { await errDlg.ShowAsync(); } catch { }
                return;
            }

            // 2) 儲存
            SaveUIToConfig();
            await SaveConfigSilentlyAsync();

            // 3) 啟動 Python 腳本並結束本程式
            TryLaunchPythonAndExit();
        }

        private static string? FindDirectoryUpwards(string startPath, string targetFolderName)
        {
            try
            {
                DirectoryInfo? dir = new DirectoryInfo(startPath);
                while (dir != null)
                {
                    var candidate = Path.Combine(dir.FullName, targetFolderName);
                    if (Directory.Exists(candidate))
                    {
                        return candidate;
                    }
                    dir = dir.Parent;
                }
            }
            catch { }
            return null;
        }

        private static void WriteLauncherLog(string message)
        {
            try
            {
                string logPath = Path.Combine(AppContext.BaseDirectory, "launcher.log");
                File.AppendAllText(logPath, $"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {message}\n");
            }
            catch { }
        }

        private void TryLaunchPythonAndExit()
        {
            try
            {
                string baseDir = AppContext.BaseDirectory;
                string? undetectedDir = FindDirectoryUpwards(baseDir, "undetected-chromedriver")
                                        ?? Path.Combine(Directory.GetCurrentDirectory(), "undetected-chromedriver");

                string pyMain = Path.Combine(undetectedDir, "main.py");
                string pyExe = Path.Combine(undetectedDir, "venv", "Scripts", "python.exe");

                WriteLauncherLog($"baseDir={baseDir}");
                WriteLauncherLog($"undetectedDir={undetectedDir}");
                WriteLauncherLog($"pyExeExists={File.Exists(pyExe)} pyMainExists={File.Exists(pyMain)}");

                if (!File.Exists(pyMain) || !File.Exists(pyExe))
                {
                    if (_isClosed) { Application.Current.Exit(); return; }
                    ContentDialog err = new()
                    {
                        Title = "啟動失敗",
                        Content = "找不到 Python 或 main.py。\n請確認已建立 venv 並安裝需求套件：\n" +
                                  "python -m venv undetected-chromedriver/venv\n" +
                                  "undetected-chromedriver/venv/Scripts/python.exe -m pip install -r undetected-chromedriver/requirements.txt",
                        CloseButtonText = "確定",
                        XamlRoot = (this.Content as FrameworkElement)?.XamlRoot
                    };
                    _ = err.ShowAsync();
                    return;
                }

                var psi = new ProcessStartInfo
                {
                    FileName = pyExe,
                    Arguments = $"\"{pyMain}\"",
                    WorkingDirectory = undetectedDir,
                    UseShellExecute = false,
                    CreateNoWindow = false
                };
                _ = Process.Start(psi);
            }
            catch (Exception ex)
            {
                WriteLauncherLog($"launch-exception: {ex}");
                if (_isClosed) { Application.Current.Exit(); return; }
                ContentDialog err = new()
                {
                    Title = "啟動失敗",
                    Content = $"無法啟動 Python：{ex.Message}",
                    CloseButtonText = "確定",
                    XamlRoot = (this.Content as FrameworkElement)?.XamlRoot
                };
                _ = err.ShowAsync();
                return;
            }

            Application.Current.Exit();
        }

        // 設定時間選擇狀態
        private DateTimeOffset selectedDateTime = DateTimeOffset.Now;
        private void ConfirmDate(object sender, RoutedEventArgs e)
        {
            if (DateCalendar.SelectedDates.Count == 0) return;
            var d = DateCalendar.SelectedDates[0];
            selectedDateTime = new DateTimeOffset(
                d.Year, d.Month, d.Day,
                selectedDateTime.Hour,
                selectedDateTime.Minute,
                selectedDateTime.Second,
                selectedDateTime.Offset);
            DatePickerButton.Content = selectedDateTime.ToString("yyyy/MM/dd", new CultureInfo("zh-TW"));
            UserConfig.Instance.SaleTime = selectedDateTime;
            UpdateInlineValidation();
        }


        private void ConfirmTime(object sender, RoutedEventArgs e)
        {
            // 從輸入框讀取數值
            if (!int.TryParse(HourBox.Text, out int h)) return;
            if (!int.TryParse(MinuteBox.Text, out int m)) return;
            if (!int.TryParse(SecondBox.Text, out int s)) return;

            // AM/PM 轉換
            if (AmPmToggle.IsOn)      // AM
            {
                if (h == 12) h = 0;
            }
            else                      // PM
            {
                if (h != 12) h += 12;
            }

            // 更新時間（保留原本的時區 Offset）
            selectedDateTime = new DateTimeOffset(
                selectedDateTime.Year,
                selectedDateTime.Month,
                selectedDateTime.Day,
                h, m, s,
                selectedDateTime.Offset);

            // 更新顯示並寫回設定
            var culture = new CultureInfo("zh-TW");
            TimePickerButton.Content = selectedDateTime.ToString("tt hh:mm:ss", culture);
            UserConfig.Instance.SaleTime = selectedDateTime;
            UpdateInlineValidation();
        }

        private void SaveUIToConfig()
        {
            var config = UserConfig.Instance;

            config.Username = NameTextBox.Text;
            config.Password = PasswordTextBox.Password;
            config.TicketName1 = TicketName1TextBox.Text;
            config.TicketName2 = TicketName2TextBox.Text;
            config.TicketPrice = PriceTextBox.Text;
            config.TicketQuantity = QuantityTextBox.Text;
            config.TicketUrl = TargetUrlTextBox.Text;
            config.IsAutoAllocation = SeatAutoRadioButton.IsChecked == true;
            config.IsAutoPayment = PaymentAutoRadioButton.IsChecked == true;

            config.SaleTime = selectedDateTime;
        }


        private static readonly JsonSerializerOptions JsonOptions = new()
        {
            WriteIndented = true
        };

        private StringBuilder ValidateInputs()
        {
            var sb = new StringBuilder();

            static bool IsBlank(string? s) => string.IsNullOrWhiteSpace(s);

            if (IsBlank(NameTextBox.Text)) sb.AppendLine("- 帳號不可為空或空白");
            if (IsBlank(PasswordTextBox.Password)) sb.AppendLine("- 密碼不可為空或空白");
            if (IsBlank(TicketName1TextBox.Text)) sb.AppendLine("- 票名(第一行)不可為空或空白");
            if (IsBlank(PriceTextBox.Text)) sb.AppendLine("- 票價不可為空或空白");
            if (IsBlank(QuantityTextBox.Text)) sb.AppendLine("- 票數不可為空或空白");
            if (IsBlank(TargetUrlTextBox.Text)) sb.AppendLine("- 搶票 URL 不可為空或空白");

            // 票價：僅數字，不可包含逗號、負號
            var price = PriceTextBox.Text?.Trim() ?? string.Empty;
            if (!DigitsRegex().IsMatch(price))
            {
                sb.AppendLine("- 票價格式錯誤：僅能包含數字，不得有逗號或負號");
            }

            // 票數：正整數 (>0)
            var qtyText = QuantityTextBox.Text?.Trim() ?? string.Empty;
            if (!DigitsRegex().IsMatch(qtyText) || !int.TryParse(qtyText, out int qty) || qty <= 0)
            {
                sb.AppendLine("- 票數格式錯誤：必須為大於 0 的整數");
            }

            // URL 格式：https://kktix.com/events/{內容}/registrations/new
            var url = TargetUrlTextBox.Text?.Trim() ?? string.Empty;
            if (url.Length > 0)
            {
                if (!Uri.TryCreate(url, UriKind.Absolute, out var uri) ||
                    !string.Equals(uri.Scheme, "https", StringComparison.OrdinalIgnoreCase) ||
                    !string.Equals(uri.Host, "kktix.com", StringComparison.OrdinalIgnoreCase))
                {
                    sb.AppendLine("- 搶票 URL 必須以 https://kktix.com/events/ 開頭，並以 /registrations/new 結尾");
                }
                else
                {
                    var segments = uri.AbsolutePath.Split('/', StringSplitOptions.RemoveEmptyEntries);
                    if (segments.Length < 4 ||
                        !string.Equals(segments[0], "events", StringComparison.OrdinalIgnoreCase) ||
                        string.IsNullOrWhiteSpace(segments[1]) ||
                        !string.Equals(segments[2], "registrations", StringComparison.OrdinalIgnoreCase) ||
                        !string.Equals(segments[3], "new", StringComparison.OrdinalIgnoreCase))
                    {
                        sb.AppendLine("- 搶票 URL 格式需為 https://kktix.com/events/{內容}/registrations/new（{內容} 不可為空）");
                    }
                }
            }

            // 開賣時間需在當前時間之後
            var now = DateTimeOffset.Now;
            if (selectedDateTime <= now)
            {
                sb.AppendLine("- 開賣時間不可早於或等於現在");
            }

            return sb;
        }

        private void UpdateInlineValidation()
        {
            static bool IsBlank(string? s) => string.IsNullOrWhiteSpace(s);

            NameErrorText.Text = IsBlank(NameTextBox.Text) ? "帳號不可為空或空白" : string.Empty;
            NameErrorText.Visibility = string.IsNullOrEmpty(NameErrorText.Text) ? Visibility.Collapsed : Visibility.Visible;

            PasswordErrorText.Text = IsBlank(PasswordTextBox.Password) ? "密碼不可為空或空白" : string.Empty;
            PasswordErrorText.Visibility = string.IsNullOrEmpty(PasswordErrorText.Text) ? Visibility.Collapsed : Visibility.Visible;

            TicketName1ErrorText.Text = IsBlank(TicketName1TextBox.Text) ? "票名(第一行)不可為空或空白" : string.Empty;
            TicketName1ErrorText.Visibility = string.IsNullOrEmpty(TicketName1ErrorText.Text) ? Visibility.Collapsed : Visibility.Visible;

            // 票價
            var price = (PriceTextBox.Text ?? string.Empty).Trim();
            bool priceOk = DigitsRegex().IsMatch(price);
            PriceErrorText.Text = priceOk ? string.Empty : "票價僅能為數字，且不可含逗號與負號";
            PriceErrorText.Visibility = string.IsNullOrEmpty(PriceErrorText.Text) ? Visibility.Collapsed : Visibility.Visible;

            // 票數
            var qtyText = (QuantityTextBox.Text ?? string.Empty).Trim();
            bool qtyOk = DigitsRegex().IsMatch(qtyText) && int.TryParse(qtyText, out int qty) && qty > 0;
            QuantityErrorText.Text = qtyOk ? string.Empty : "票數需為大於 0 的整數";
            QuantityErrorText.Visibility = string.IsNullOrEmpty(QuantityErrorText.Text) ? Visibility.Collapsed : Visibility.Visible;

            // URL 僅允許 kktix.com
            var url = (TargetUrlTextBox.Text ?? string.Empty).Trim();
            string urlErr = string.Empty;
            if (IsBlank(url))
            {
                urlErr = "搶票 URL 不可為空或空白";
            }
            else if (!Uri.TryCreate(url, UriKind.Absolute, out var uri) || !string.Equals(uri.Scheme, "https", StringComparison.OrdinalIgnoreCase) || !string.Equals(uri.Host, "kktix.com", StringComparison.OrdinalIgnoreCase))
            {
                urlErr = "必須以 https://kktix.com/events/ 開頭，並以 /registrations/new 結尾";
            }
            else
            {
                var seg = uri.AbsolutePath.Split('/', StringSplitOptions.RemoveEmptyEntries);
                if (seg.Length < 4 || !string.Equals(seg[0], "events", StringComparison.OrdinalIgnoreCase) || string.IsNullOrWhiteSpace(seg[1]) || !string.Equals(seg[2], "registrations", StringComparison.OrdinalIgnoreCase) || !string.Equals(seg[3], "new", StringComparison.OrdinalIgnoreCase))
                {
                    urlErr = "URL 格式需為 https://kktix.com/events/{內容}/registrations/new（{內容} 不可為空）";
                }
            }
            UrlErrorText.Text = urlErr;
            UrlErrorText.Visibility = string.IsNullOrEmpty(urlErr) ? Visibility.Collapsed : Visibility.Visible;

            // 時間
            var now = DateTimeOffset.Now;
            TimeErrorText.Text = selectedDateTime <= now ? "開賣時間不可早於或等於現在" : string.Empty;
            TimeErrorText.Visibility = string.IsNullOrEmpty(TimeErrorText.Text) ? Visibility.Collapsed : Visibility.Visible;

            // 控制開始按鈕可用性
            bool hasError = !(string.IsNullOrEmpty(NameErrorText.Text)
                              && string.IsNullOrEmpty(PasswordErrorText.Text)
                              && string.IsNullOrEmpty(TicketName1ErrorText.Text)
                              && string.IsNullOrEmpty(PriceErrorText.Text)
                              && string.IsNullOrEmpty(QuantityErrorText.Text)
                              && string.IsNullOrEmpty(UrlErrorText.Text)
                              && string.IsNullOrEmpty(TimeErrorText.Text));
            StartButton.IsEnabled = !hasError;
        }

        private void OnFormChanged(object sender, TextChangedEventArgs e)
        {
            UpdateInlineValidation();
        }

        private void OnPasswordChanged(object sender, RoutedEventArgs e)
        {
            UpdateInlineValidation();
        }

        private async Task SaveConfigSilentlyAsync()
        {
            try
            {
                string exePath = Path.Combine(AppContext.BaseDirectory, "UserConfig.json");
                string localDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "kktix");
                string localPath = Path.Combine(localDir, "UserConfig.json");
                var utf8NoBom = new UTF8Encoding(false);
                string jsonString = JsonSerializer.Serialize(UserConfig.Instance, JsonOptions);

                try
                {
                    await File.WriteAllTextAsync(exePath, jsonString, utf8NoBom);
                }
                catch
                {
                    Directory.CreateDirectory(localDir);
                    await File.WriteAllTextAsync(localPath, jsonString, utf8NoBom);
                }
            }
            catch (Exception ex)
            {
                if (_isClosed) return;
                ContentDialog errorDialog = new()
                {
                    Title = "儲存失敗",
                    Content = $"無法儲存設定：{ex.Message}",
                    CloseButtonText = "確定",
                    XamlRoot = (this.Content as FrameworkElement)?.XamlRoot
                };
                try { await errorDialog.ShowAsync(); } catch { }
            }
        }

        // 顯示/隱藏密碼切換
        private void PasswordRevealToggle_Checked(object sender, RoutedEventArgs e)
        {
            try
            {
                PasswordTextBox.PasswordRevealMode = PasswordRevealMode.Visible;
            }
            catch { }
        }

        private void PasswordRevealToggle_Unchecked(object sender, RoutedEventArgs e)
        {
            try
            {
                PasswordTextBox.PasswordRevealMode = PasswordRevealMode.Hidden;
            }
            catch { }
        }
        private async Task SaveConfigWithDialogAsync()
        {
            try
            {
                string exePath = Path.Combine(AppContext.BaseDirectory, "UserConfig.json");
                string localDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "kktix");
                string localPath = Path.Combine(localDir, "UserConfig.json");
                var utf8NoBom = new UTF8Encoding(false);
                string jsonString = JsonSerializer.Serialize(UserConfig.Instance, JsonOptions);
                string savedPath = exePath;
                try
                {
                    await File.WriteAllTextAsync(exePath, jsonString, utf8NoBom);
                }
                catch
                {
                    Directory.CreateDirectory(localDir);
                    await File.WriteAllTextAsync(localPath, jsonString, utf8NoBom);
                    savedPath = localPath;
                }

                // 儲存成功提示
                if (_isClosed) return;
                ContentDialog successDialog = new()
                {
                    Title = "已儲存",
                    Content = $"設定資料已成功儲存！\n路徑：{savedPath}",
                    CloseButtonText = "確定",
                    XamlRoot = (this.Content as FrameworkElement)?.XamlRoot
                };
                try { await successDialog.ShowAsync(); } catch { }
            }
            catch (Exception ex)
            {
                // 儲存錯誤提示
                if (_isClosed) return;
                ContentDialog errorDialog = new()
                {
                    Title = "儲存失敗",
                    Content = $"無法儲存設定：{ex.Message}",
                    CloseButtonText = "確定",
                    XamlRoot = (this.Content as FrameworkElement)?.XamlRoot
                };
                try { await errorDialog.ShowAsync(); } catch { }
            }
        }
    }
}
