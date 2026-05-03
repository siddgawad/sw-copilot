using System;
using System.Collections.ObjectModel;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using SolidWorks.Interop.sldworks;
using SwCopilotAddin.Client;
using SwCopilotAddin.Execution;

namespace SwCopilotAddin.UI
{
    public partial class ChatPanel : System.Windows.Controls.UserControl
    {
        private readonly ISldWorks _swApp;
        private readonly BackendClient _client;
        private readonly DocumentContextBuilder _contextBuilder;
        private readonly ObservableCollection<ChatMessage> _messages = new();

        public ChatPanel(ISldWorks swApp)
        {
            InitializeComponent();
            _swApp          = swApp;
            _client         = new BackendClient();
            _contextBuilder = new DocumentContextBuilder(swApp);
            MessageList.ItemsSource = _messages;
        }

        private async void SendButton_Click(object sender, RoutedEventArgs e) => await SubmitAsync();

        private async void InputBox_KeyDown(object sender, KeyEventArgs e)
        {
            if (e.Key == Key.Enter && !Keyboard.IsKeyDown(Key.LeftShift))
                await SubmitAsync();
        }

        private async Task SubmitAsync()
        {
            string prompt = InputBox.Text.Trim();
            if (string.IsNullOrEmpty(prompt)) return;

            InputBox.Clear();
            AddMessage(prompt, isUser: true);
            SetStatus("Contacting agent…");
            SendButton.IsEnabled = false;

            try
            {
                DocumentContext ctx      = _contextBuilder.Build();
                AgentResponse   response = await _client.SendPromptAsync(prompt, ctx);

                AddMessage(response.StatusMessage, isUser: false);

                if (!string.IsNullOrEmpty(response.MacroCode))
                {
                    SetStatus("Executing macro…");
                    var    executor = new MacroExecutor(_swApp);
                    string result   = executor.Execute(response.MacroCode);
                    SetStatus(result);
                }
                else
                {
                    SetStatus("Ready");
                }
            }
            catch (Exception ex)
            {
                AddMessage($"Error: {ex.Message}", isUser: false);
                SetStatus("Error — check the message above");
            }
            finally
            {
                SendButton.IsEnabled = true;
            }
        }

        private static readonly SolidColorBrush UserBubble   = new(Color.FromRgb(0x31, 0x32, 0x44));
        private static readonly SolidColorBrush AgentBubble  = new(Color.FromRgb(0x18, 0x18, 0x25));

        private void AddMessage(string text, bool isUser)
        {
            _messages.Add(new ChatMessage
            {
                Text       = text,
                Background = isUser ? UserBubble : AgentBubble,
                Alignment  = isUser ? HorizontalAlignment.Right : HorizontalAlignment.Left,
            });
            ChatScroll.ScrollToBottom();
        }

        private void SetStatus(string msg) => StatusText.Text = msg;
    }

    public sealed class ChatMessage
    {
        public string              Text       { get; set; } = string.Empty;
        public Brush               Background { get; set; } = Brushes.Transparent;
        public HorizontalAlignment Alignment  { get; set; } = HorizontalAlignment.Left;
    }
}
