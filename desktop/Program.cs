using System.Diagnostics;
using System.Net.Http;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using System.Windows.Forms;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new ForgeMindWindow());
    }
}

internal sealed class ForgeMindWindow : Form
{
    private const string Service = "http://127.0.0.1:8094/";
    private static readonly HttpClient Client = new() { Timeout = TimeSpan.FromSeconds(2) };
    private readonly WebView2 view = new() { Dock = DockStyle.Fill };
    private readonly Label status = new()
    {
        Dock = DockStyle.Fill,
        TextAlign = System.Drawing.ContentAlignment.MiddleCenter,
        Text = "正在检查 ForgeMind 本地服务…"
    };

    public ForgeMindWindow()
    {
        Text = "ForgeMind 本地 AI";
        Width = 1320;
        Height = 860;
        MinimumSize = new System.Drawing.Size(900, 600);
        Controls.Add(status);
        Shown += OpenService;
    }

    private async void OpenService(object? sender, EventArgs e)
    {
        try
        {
            var root = FindDeploymentRoot();
            if (!await IsServiceReady())
            {
                if (root is null)
                {
                    using var picker = new FolderBrowserDialog
                    {
                        Description = "请选择 ForgeMind-Portable 部署目录（需包含 scripts、models 和 runtime）",
                        UseDescriptionForTitle = true
                    };
                    if (picker.ShowDialog(this) != DialogResult.OK)
                        return;
                    root = picker.SelectedPath;
                    if (!IsDeploymentRoot(root))
                        throw new DirectoryNotFoundException("所选目录不是完整的 ForgeMind 部署目录。请确认其中包含 scripts/run_windows.ps1、models 和 runtime/windows/llama-server.exe。");
                }

                status.Text = "正在启动 ForgeMind 模型和网页服务。首次启动可能需要几分钟…";
                await StartDeployment(root);
            }

            var profile = Path.Combine(AppContext.BaseDirectory, "runstate", "webview2");
            Directory.CreateDirectory(profile);
            var environment = await CoreWebView2Environment.CreateAsync(userDataFolder: profile);
            await view.EnsureCoreWebView2Async(environment);
            view.CoreWebView2.Settings.AreDevToolsEnabled = false;
            view.CoreWebView2.Settings.IsStatusBarEnabled = false;
            view.CoreWebView2.NewWindowRequested += (_, args) =>
            {
                args.Handled = true;
                OpenExternal(args.Uri);
            };
            view.CoreWebView2.NavigationStarting += (_, args) =>
            {
                if (!args.Uri.StartsWith(Service, StringComparison.OrdinalIgnoreCase))
                {
                    args.Cancel = true;
                    OpenExternal(args.Uri);
                }
            };
            Controls.Remove(status);
            Controls.Add(view);
            view.Source = new Uri(Service);
        }
        catch (Exception ex)
        {
            MessageBox.Show(this,
                "ForgeMind 启动失败。请检查部署包中的 logs 文件夹。\n\n" + ex.Message,
                "ForgeMind 启动失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
            Close();
        }
    }

    private static async Task<bool> IsServiceReady()
    {
        try
        {
            using var response = await Client.GetAsync(Service + "healthz");
            return response.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
    }

    private static string? FindDeploymentRoot()
    {
        var candidates = new[]
        {
            Environment.GetEnvironmentVariable("FORGEMIND_DEPLOYMENT_DIR"),
            Path.Combine(AppContext.BaseDirectory, "ForgeMind-Portable-2026-10-12"),
            @"D:\simon\ForgeMind-Work\project\output\ForgeMind-Portable-2026-10-12"
        };
        return candidates.FirstOrDefault(path => !string.IsNullOrWhiteSpace(path) && IsDeploymentRoot(path));
    }

    private static bool IsDeploymentRoot(string path) =>
        File.Exists(Path.Combine(path, "scripts", "run_windows.ps1")) &&
        File.Exists(Path.Combine(path, "models", "qwen2.5-coder-7b-instruct-q4_k_m.gguf")) &&
        File.Exists(Path.Combine(path, "runtime", "windows", "llama-server.exe"));

    private async Task StartDeployment(string root)
    {
        var script = Path.Combine(root, "scripts", "run_windows.ps1");
        if (!IsDeploymentRoot(root))
            throw new DirectoryNotFoundException("未找到完整的 ForgeMind 部署包：" + root);

        var start = new ProcessStartInfo("powershell.exe")
        {
            WorkingDirectory = root,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        start.ArgumentList.Add("-NoProfile");
        start.ArgumentList.Add("-ExecutionPolicy");
        start.ArgumentList.Add("Bypass");
        start.ArgumentList.Add("-File");
        start.ArgumentList.Add(script);
        start.Environment["FORGEMIND_LAUNCHER"] = "1";

        using var process = Process.Start(start) ?? throw new InvalidOperationException("无法启动部署脚本。");
        var stdout = process.StandardOutput.ReadToEndAsync();
        var stderr = process.StandardError.ReadToEndAsync();
        for (var seconds = 0; seconds < 900; seconds++)
        {
            if (await IsServiceReady())
                return;
            if (process.HasExited)
            {
                var details = (await stderr + Environment.NewLine + await stdout).Trim();
                if (details.Length > 1800)
                    details = details[^1800..];
                throw new InvalidOperationException("部署脚本已退出。\n" + details);
            }
            if (seconds % 5 == 0)
                status.Text = $"正在启动 ForgeMind 本地模型…已等待 {seconds} 秒";
            await Task.Delay(1000);
        }
        throw new TimeoutException($"等待网页服务超时。请查看部署目录的 logs 文件夹：{root}");
    }

    private static void OpenExternal(string uri)
    {
        if (Uri.TryCreate(uri, UriKind.Absolute, out var parsed) && parsed.Scheme is "http" or "https")
            Process.Start(new ProcessStartInfo(uri) { UseShellExecute = true });
    }
}
