using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace SwCopilotAddin.Client
{
    public sealed class BackendClient
    {
        private const int MaxHistoryMessages = 8;
        private const int MaxHistoryContentChars = 3000;

        // Single shared HttpClient — not recreated per request.
        private static readonly HttpClient _http = new HttpClient
        {
            Timeout = System.TimeSpan.FromSeconds(60),
        };

        // Override via environment variable SW_COPILOT_BACKEND_URL for remote deployments.
        // Use 127.0.0.1 by default because uvicorn is bound to IPv4; "localhost"
        // can resolve to ::1 first and fail from .NET Framework inside SolidWorks.
        private static readonly string BaseUrl =
            System.Environment.GetEnvironmentVariable("SW_COPILOT_BACKEND_URL")
            ?? "http://127.0.0.1:8001";

        public async Task<AgentResponse> SendPromptAsync(
            string prompt,
            DocumentContext context,
            IReadOnlyList<ConversationMessage>? history = null)
        {
            await BackendRuntime.EnsureReadyAsync(_http, BaseUrl);

            var payload = new
            {
                prompt,
                context = new
                {
                    document_type   = context.DocumentType,
                    body_count      = context.BodyCount,
                    selected_ids    = context.SelectedEntityIds,
                    file_path       = context.FilePath,
                    bounding_box_mm = context.BoundingBoxMm == null
                        ? null
                        : new
                        {
                            x_mm = context.BoundingBoxMm.XMm,
                            y_mm = context.BoundingBoxMm.YMm,
                            z_mm = context.BoundingBoxMm.ZMm,
                        },
                },
                messages = BuildHistoryPayload(history),
            };

            string json    = JsonConvert.SerializeObject(payload);
            var    content = new StringContent(json, Encoding.UTF8, "application/json");

            HttpResponseMessage response;
            try
            {
                using var request = new HttpRequestMessage(HttpMethod.Post, $"{BaseUrl.TrimEnd('/')}/generate")
                {
                    Content = content,
                };
                request.Headers.Add("X-Copilot-Token", BackendRuntime.ReadToken());
                response = await _http.SendAsync(request);
            }
            catch (TaskCanceledException ex)
            {
                throw new System.InvalidOperationException(
                    $"Backend request timed out after {_http.Timeout.TotalSeconds:0} seconds. URL: {BaseUrl}. " +
                    "Check that the backend is running on http://127.0.0.1:8001/health.",
                    ex);
            }
            catch (HttpRequestException ex)
            {
                throw new System.InvalidOperationException(
                    $"Could not reach backend at {BaseUrl}. " +
                    "Check that uvicorn is running and that SW_COPILOT_BACKEND_URL is not pointing to the wrong port.",
                    ex);
            }

            string body = await response.Content.ReadAsStringAsync();
            if (!response.IsSuccessStatusCode)
            {
                throw new System.InvalidOperationException(
                    $"Backend returned HTTP {(int)response.StatusCode} {response.ReasonPhrase}: {body}");
            }

            return JsonConvert.DeserializeObject<AgentResponse>(body)
                   ?? new AgentResponse { StatusMessage = "Empty response from backend." };
        }

        private static object[] BuildHistoryPayload(IReadOnlyList<ConversationMessage>? history)
        {
            if (history == null || history.Count == 0)
                return System.Array.Empty<object>();

            int skip = System.Math.Max(0, history.Count - MaxHistoryMessages);
            return history
                .Skip(skip)
                .Select(m => new
                {
                    role = m.Role,
                    content = TrimHistoryContent(m.Content),
                })
                .Cast<object>()
                .ToArray();
        }

        private static string TrimHistoryContent(string content)
        {
            if (content.Length <= MaxHistoryContentChars)
                return content;
            return content.Substring(0, MaxHistoryContentChars) + "\n... [history truncated]";
        }

        public async Task<ValidationResponse> ValidateOperationAsync(
            OperationGraphDto operationGraph,
            string partReportJson,
            string? executorResultJson = null,
            double toleranceMm = 1.0)
        {
            await BackendRuntime.EnsureReadyAsync(_http, BaseUrl);

            JObject partReport = JObject.Parse(partReportJson);
            JObject? executorResult = string.IsNullOrWhiteSpace(executorResultJson)
                ? null
                : JObject.Parse(executorResultJson!);
            var payload = new
            {
                operation_graph = operationGraph,
                part_report = partReport,
                executor_result = executorResult,
                tolerance_mm = toleranceMm,
            };

            string json = JsonConvert.SerializeObject(payload);
            var content = new StringContent(json, Encoding.UTF8, "application/json");

            HttpResponseMessage response;
            try
            {
                using var request = new HttpRequestMessage(HttpMethod.Post, $"{BaseUrl.TrimEnd('/')}/validate")
                {
                    Content = content,
                };
                request.Headers.Add("X-Copilot-Token", BackendRuntime.ReadToken());
                response = await _http.SendAsync(request);
            }
            catch (TaskCanceledException ex)
            {
                throw new System.InvalidOperationException(
                    $"Backend validation timed out after {_http.Timeout.TotalSeconds:0} seconds. URL: {BaseUrl}.",
                    ex);
            }
            catch (HttpRequestException ex)
            {
                throw new System.InvalidOperationException(
                    $"Could not reach backend validation endpoint at {BaseUrl}.",
                    ex);
            }

            string body = await response.Content.ReadAsStringAsync();
            if (!response.IsSuccessStatusCode)
            {
                if ((int)response.StatusCode == 404)
                {
                    throw new System.InvalidOperationException(
                        "Backend validation endpoint /validate was not found. " +
                        "This usually means SolidWorks is talking to an old packaged backend; stop SwCopilotBackend.exe, rebuild/reinstall the beta package, or point SW_COPILOT_BACKEND_EXE at the current backend. " +
                        $"URL: {BaseUrl}.");
                }

                throw new System.InvalidOperationException(
                    $"Backend validation returned HTTP {(int)response.StatusCode} {response.ReasonPhrase}: {body}");
            }

            return JsonConvert.DeserializeObject<ValidationResponse>(body)
                   ?? new ValidationResponse
                   {
                       Passed = false,
                       Discrepancies = new[]
                       {
                           new ValidationDiscrepancy
                           {
                               Category = "response",
                               Severity = "error",
                               Message = "Empty validation response from backend.",
                           },
                       },
                   };
        }
    }

    public sealed class ConversationMessage
    {
        public string Role    { get; }
        public string Content { get; }
        public ConversationMessage(string role, string content)
        {
            Role    = role;
            Content = content;
        }
    }

    public sealed class AgentResponse
    {
        [JsonProperty("macro_code")]
        public string? MacroCode { get; set; }

        [JsonProperty("cad_command")]
        public CadCommandDto? CadCommand { get; set; }

        [JsonProperty("operation_graph")]
        public OperationGraphDto? OperationGraph { get; set; }

        [JsonProperty("status_message")]
        public string StatusMessage { get; set; } = string.Empty;

        [JsonProperty("rag_sources")]
        public string[] RagSources { get; set; } = System.Array.Empty<string>();
    }

    public sealed class ValidationResponse
    {
        [JsonProperty("passed")]
        public bool Passed { get; set; }

        [JsonProperty("has_warnings")]
        public bool HasWarnings { get; set; }

        [JsonProperty("discrepancies")]
        public ValidationDiscrepancy[] Discrepancies { get; set; } = System.Array.Empty<ValidationDiscrepancy>();

        [JsonProperty("expected_summary")]
        public Dictionary<string, object> ExpectedSummary { get; set; } = new Dictionary<string, object>();

        [JsonProperty("actual_summary")]
        public Dictionary<string, object> ActualSummary { get; set; } = new Dictionary<string, object>();
    }

    public sealed class ValidationDiscrepancy
    {
        [JsonProperty("category")]
        public string Category { get; set; } = string.Empty;

        [JsonProperty("severity")]
        public string Severity { get; set; } = string.Empty;

        [JsonProperty("expected")]
        public string Expected { get; set; } = string.Empty;

        [JsonProperty("actual")]
        public string Actual { get; set; } = string.Empty;

        [JsonProperty("message")]
        public string Message { get; set; } = string.Empty;
    }
}
