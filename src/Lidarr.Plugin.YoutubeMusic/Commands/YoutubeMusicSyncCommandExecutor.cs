using NzbDrone.Core.Messaging.Commands;
using NzbDrone.Core.Plugins.Services;

namespace NzbDrone.Core.Plugins
{
    /// <summary>
    /// Executor for <see cref="YoutubeMusicSyncCommand"/>. Resolves the settings
    /// the provider captured and delegates to the Python bridge. On success it
    /// reports the outcome via the command completion toast in the Lidarr UI.
    /// </summary>
    public class YoutubeMusicSyncCommandExecutor : IExecute<YoutubeMusicSyncCommand>
    {
        private readonly YoutubeMusicProcessRunner _runner;

        public YoutubeMusicSyncCommandExecutor(YoutubeMusicProcessRunner runner)
        {
            _runner = runner;
        }

        public void Execute(YoutubeMusicSyncCommand message)
        {
            var settings = YoutubeMusicRunContext.Current ?? new YoutubeMusicSettings();
            var exit = _runner.Run(settings);
            message.SetResultMessage(
                exit == 0
                    ? "YouTube Music sync completed successfully."
                    : $"YouTube Music sync exited with code {exit} (see Lidarr log).");
        }
    }
}