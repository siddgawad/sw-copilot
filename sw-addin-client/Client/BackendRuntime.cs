using System;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;

namespace SwCopilotAddin.Client
{
    internal static class BackendRuntime
    {
        private const string BackendExeName = "SwCopilotBackend.exe";
        private const string CurrentVersion = "0.1.0";
        private static readonly HttpClient GitHubHttp = new HttpClient
        {
            Timeout = System.TimeSpan.FromSeconds(20),
        };
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

        public static string? GetReleaseRepository()
        {
            string? repo = Environment.GetEnvironmentVariable("SW_COPILOT_GITHUB_REPO");
            if (!string.IsNullOrWhiteSpace(repo))
                return repo.Trim();

            repo = Environment.GetEnvironmentVariable("SW_COPILOT_RELEASE_REPO");
            if (!string.IsNullOrWhiteSpace(repo))
                return repo.Trim();

            return null;
        }

        public static async Task<GitHubReleaseInfo?> CheckForUpdateAsync()
        {
            string repo = (GetReleaseRepository() ?? string.Empty).Trim();
            if (string.IsNullOrWhiteSpace(repo))
                return null;

            string url = $"https://api.github.com/repos/{repo}/releases/latest";

            using var request = new HttpRequestMessage(HttpMethod.Get, url);
            request.Headers.UserAgent.ParseAdd("SwCopilotAddin/0.1.0");
            request.Headers.Accept.ParseAdd("application/vnd.github+json");
            request.Headers.TryAddWithoutValidation("X-GitHub-Api-Version", "2022-11-28");

            using HttpResponseMessage response = await GitHubHttp.SendAsync(request).ConfigureAwait(false);
            string body = await response.Content.ReadAsStringAsync().ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
                return null;

            GitHubReleasePayload? payload = JsonConvert.DeserializeObject<GitHubReleasePayload>(body);
            string latestTag = NormalizeTag(payload?.TagName) ?? string.Empty;
            if (string.IsNullOrWhiteSpace(latestTag))
                return null;

            if (!IsNewerVersion(latestTag, CurrentVersion))
                return null;

            return new GitHubReleaseInfo
            {
                Version = latestTag,
                Url = string.IsNullOrWhiteSpace(payload?.HtmlUrl)
                    ? $"https://github.com/{repo}/releases/latest"
                    : payload!.HtmlUrl!,
            };
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

        private static string? NormalizeTag(string? tag)
        {
            if (string.IsNullOrWhiteSpace(tag))
                return null;

            string value = tag!.Trim();
            if (value.StartsWith("v", StringComparison.OrdinalIgnoreCase))
                value = value.Substring(1);
            return value;
        }

        private static bool IsNewerVersion(string candidate, string current)
        {
            if (!Version.TryParse(candidate, out Version? candidateVersion))
                return false;
            if (!Version.TryParse(current, out Version? currentVersion))
                return false;
            return candidateVersion > currentVersion;
        }

        private sealed class GitHubReleasePayload
        {
            [JsonProperty("tag_name")]
            public string? TagName { get; set; }

            [JsonProperty("html_url")]
            public string? HtmlUrl { get; set; }
        }
    }

    public sealed class GitHubReleaseInfo
    {
        public string Version { get; set; } = string.Empty;
        public string Url { get; set; } = string.Empty;
    }
}
