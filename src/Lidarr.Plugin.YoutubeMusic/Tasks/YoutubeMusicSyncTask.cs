using System;
using NLog;
using NzbDrone.Core.Messaging.Commands;
using NzbDrone.Core.Plugins.Scheduling;

namespace NzbDrone.Core.Plugins
{
    /// <summary>
    /// Scheduled "YouTube Music Sync Scan" entry (Settings &gt; Metadata) that also runs
    /// the sync when fired. Merging <see cref="IExecute{TCommand}"/> into the metadata
    /// provider (rather than using a separate executor service) avoids a DryIoc
    /// recursive dependency at startup: this resolver only depends on the lightweight
    /// process runner and NLog, never on provider factories or other plugins.
    /// </summary>
    public class YoutubeMusicSyncTask : ScheduledTaskBase<YoutubeMusicSettings>, IExecute<YoutubeMusicSyncCommand>
    {
        private readonly YoutubeMusicProcessRunner _runner;
        private readonly Logger _logger;

        public YoutubeMusicSyncTask(YoutubeMusicProcessRunner runner, Logger logger)
        {
            _runner = runner ?? throw new ArgumentNullException(nameof(runner));
            _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        }

        public override string Name => "YouTube Music Sync Scan";

        public override Type CommandType => typeof(YoutubeMusicSyncCommand);

        public override int IntervalMinutes => TryGetInterval();

        public override CommandPriority Priority => CommandPriority.Low;

        private int TryGetInterval()
        {
            try
            {
                if (Definition?.Settings is YoutubeMusicSettings settings && settings.ScanIntervalMinutes >= 60)
                {
                    return settings.ScanIntervalMinutes;
                }
            }
            catch (Exception ex)
            {
                _logger.Warn(ex, "[YTM] interval read failed, defaulting to 1440");
            }

            return 1440;
        }

        public void Execute(YoutubeMusicSyncCommand message)
        {
            if (message == null)
            {
                throw new ArgumentNullException(nameof(message));
            }

            var settings = Definition?.Settings as YoutubeMusicSettings ?? new YoutubeMusicSettings();
            var exit = _runner.Run(settings);
            message.SetResultMessage(
                exit == 0
                    ? "YouTube Music sync completed successfully."
                    : $"YouTube Music sync exited with code {exit} (see Lidarr log).");
        }
    }
}