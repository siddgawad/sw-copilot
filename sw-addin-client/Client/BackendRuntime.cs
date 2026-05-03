using System;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

namespace SwCopilotAddin.Client
{
    internal static class BackendRuntime
    {
        private const string BackendExeName = "SwCopilotBackend.exe";
        private static readonly SemaphoreSlim StartupGate = new SemaphoreSlim(1, 1);

        public static string TokenPath => Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "SwCopilotAddin",
            "backend.token");

        public static async Task EnsureReadyAsync(HttpClient http, string baseUrl)
        {
            if (await TryHealthAsync(http, baseUrl).ConfigureAwait(false))
                return;

            await StartupGate.WaitAsync().ConfigureAwait(false);
            try
            {
                if (await TryHealthAsync(http, baseUrl).ConfigureAwait(false))
                    return;

                string backendExe = ResolveBackendExePath();
                StartBackend(backendExe);

                DateTime deadline = DateTime.UtcNow.AddSeconds(30);
                while (DateTime.UtcNow < deadline)
                {
                    await Task.Delay(500).ConfigureAwait(false);
                    if (await TryHealthAsync(http, baseUrl).ConfigureAwait(false))
                        return;
                }

                throw new InvalidOperationException(
                    "Started backend but it did not become ready within 30 seconds. " +
                    $"Check logs under {Path.Combine(Path.GetDirectoryName(TokenPath) ?? string.Empty, "logs")}.");
            }
            finally
            {
                StartupGate.Release();
            }
        }

        public static string ReadToken()
        {
            if (!File.Exists(TokenPath))
            {
                throw new InvalidOperationException(
                    $"Backend token file was not found at {TokenPath}. The backend may not have started correctly.");
            }

            string token = File.ReadAllText(TokenPath).Trim();
            if (string.IsNullOrWhiteSpace(token))
            {
                throw new InvalidOperationException(
                    $"Backend token file is empty at {TokenPath}. Restart SW Copilot backend.");
            }

            return token;
        }

        private static async Task<bool> TryHealthAsync(HttpClient http, string baseUrl)
        {
            if (!File.Exists(TokenPath))
                return false;

            try
            {
                using var request = new HttpRequestMessage(HttpMethod.Get, $"{baseUrl.TrimEnd('/')}/health");
                request.Headers.Add("X-Copilot-Token", ReadToken());
                using HttpResponseMessage response = await http.SendAsync(request).ConfigureAwait(false);
                return response.IsSuccessStatusCode;
            }
            catch
            {
                return false;
            }
        }

        private static string ResolveBackendExePath()
        {
            string? explicitPath = Environment.GetEnvironmentVariable("SW_COPILOT_BACKEND_EXE");
            if (!string.IsNullOrWhiteSpace(explicitPath) && File.Exists(explicitPath))
                return explicitPath;

            string addinDir = Path.GetDirectoryName(typeof(BackendRuntime).Assembly.Location)
                              ?? AppDomain.CurrentDomain.BaseDirectory;

            string[] candidates =
            {
                Path.Combine(addinDir, BackendExeName),
                Path.Combine(addinDir, "backend", BackendExeName),
                Path.Combine(addinDir, "backend", "SwCopilotBackend", BackendExeName),
            };

            foreach (string candidate in candidates)
            {
                if (File.Exists(candidate))
                    return candidate;
            }

            throw new InvalidOperationException(
                $"Backend is not running and {BackendExeName} was not found. " +
                "Install the beta package or set SW_COPILOT_BACKEND_EXE to the backend executable path.");
        }

        private static void StartBackend(string backendExe)
        {
            string workingDirectory = Path.GetDirectoryName(backendExe) ?? Environment.CurrentDirectory;
            var startInfo = new ProcessStartInfo
            {
                FileName = backendExe,
                WorkingDirectory = workingDirectory,
                UseShellExecute = false,
                CreateNoWindow = true,
            };

            Process.Start(startInfo);
        }
    }
}
