using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Newtonsoft.Json;

namespace SwCopilotAddin.Client
{
    public sealed class BackendClient
    {
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
                    document_type = context.DocumentType,
                    body_count    = context.BodyCount,
                    selected_ids  = context.SelectedEntityIds,
                    file_path     = context.FilePath,
                },
                messages = (history ?? System.Array.Empty<ConversationMessage>())
                    .Select(m => new { role = m.Role, content = m.Content })
                    .ToArray(),
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
}
