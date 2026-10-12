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
    private readonly WebView2 view = new() { Dock = DockStyle.Fill };
    private const string Service = "http://127.0.0.1:8094/";

    public ForgeMindWindow()
    {
        Text = "ForgeMind 本地 AI";
        Width = 1320;
        Height = 860;
        MinimumSize = new System.Drawing.Size(900, 600);
        Controls.Add(view);
        Shown += OpenService;
    }

    private async void OpenService(object? sender, EventArgs e)
    {
        try
        {
            using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(4) };
            using var response = await client.GetAsync(Service + "healthz");
            if (!response.IsSuccessStatusCode)
                throw new InvalidOperationException("ForgeMind 本地服务没有就绪。");

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
            view.Source = new Uri(Service);
        }
        catch (Exception ex)
        {
            MessageBox.Show(this,
                "无法连接 ForgeMind 本地服务。请先在部署包中启动服务，再打开此 EXE。\n\n网页服务：http://127.0.0.1:8094/\n模型 API：http://127.0.0.1:8091/v1\n\n" + ex.Message,
                "ForgeMind 服务未就绪", MessageBoxButtons.OK, MessageBoxIcon.Information);
            Close();
        }
    }

    private static void OpenExternal(string uri)
    {
        if (Uri.TryCreate(uri, UriKind.Absolute, out var parsed) && parsed.Scheme is "http" or "https")
            Process.Start(new ProcessStartInfo(uri) { UseShellExecute = true });
    }
}
