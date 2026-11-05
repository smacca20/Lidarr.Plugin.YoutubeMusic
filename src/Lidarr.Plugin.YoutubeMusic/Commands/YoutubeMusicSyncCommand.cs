using NzbDrone.Core.Messaging.Commands;

namespace NzbDrone.Core.Plugins
{
    /// <summary>
    /// Runs the YouTube Music -> Lidarr sync. Triggered by the scheduled task
    /// (Settings &gt; Metadata) or manually from System &gt; Tasks.
    /// </summary>
    public class YoutubeMusicSyncCommand : Command
    {
        private string _resultMessage = string.Empty;

        public YoutubeMusicSyncCommand()
        {
            SendUpdatesToClient = true;
        }

        public override string CompletionMessage => _resultMessage;

        public void SetResultMessage(string message) => _resultMessage = message;
    }
}