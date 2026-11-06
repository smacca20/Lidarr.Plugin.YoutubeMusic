using System;
using System.Linq;
using System.Text;
using NLog;
using NzbDrone.Core.Extras.Metadata;
using NzbDrone.Core.Messaging.Commands;
using NzbDrone.Core.Notifications;
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
        private readonly Lazy<IMetadataFactory> _metadataFactory;
        private readonly Lazy<INotificationFactory> _notificationFactory;
        private readonly Logger _logger;

        public YoutubeMusicSyncTask(
            YoutubeMusicProcessRunner runner,
            Lazy<IMetadataFactory> metadataFactory,
            Lazy<INotificationFactory> notificationFactory,
            Logger logger)
        {
            _runner = runner ?? throw new ArgumentNullException(nameof(runner));
            _metadataFactory = metadataFactory ?? throw new ArgumentNullException(nameof(metadataFactory));
            _notificationFactory = notificationFactory ?? throw new ArgumentNullException(nameof(notificationFactory));
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
                var interval = ResolveSettings().ScanIntervalMinutes;
                if (interval >= 60)
                {
                    return interval;
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

            var settings = ResolveSettings();
            var output = new StringBuilder();
            var exit = _runner.Run(settings, onOutput: line => output.AppendLine(line));
            // This Lidarr build's Command API has no SetMessage for live line-by-line
            // streaming, so we present the full sync report via the completion message,
            // which System -> Tasks / history shows in the UI.
            message.SetResultMessage(BuildSummary(output.ToString(), exit));
        }

        /// <summary>Builds a full sync summary for the command completion message.</summary>
        private static string BuildSummary(string output, int exit)
        {
            var trimmed = (output ?? string.Empty).Trim();
            if (exit == 0)
            {
                return string.IsNullOrWhiteSpace(trimmed)
                    ? "YouTube Music sync completed successfully."
                    : trimmed;
            }

            const int keep = 2000;
            var tail = trimmed.Length > keep ? "..." + trimmed.Substring(trimmed.Length - keep) : trimmed;
            return $"YouTube Music sync exited with code {exit}. (See Lidarr log for details.)\n{tail}";
        }

        /// <summary>
        /// A manual "Run now" resolves an unbound executor whose <see cref="Definition"/>
        /// is null, so fall back to the persisted provider definitions (the metadata task
        /// entry and the Connect notification entry) to get the configured values.
        /// </summary>
        private YoutubeMusicSettings ResolveSettings()
        {
            var task = ResolveTaskSettings();
            var notif = ResolveNotificationSettings();

            var merged = new YoutubeMusicSettings
            {
                PythonExecutable = Pick(task?.PythonExecutable, notif?.PythonExecutable, YoutubeMusicSettings.DefaultPythonExecutable),
                CliProjectPath = Pick(task?.CliProjectPath, notif?.CliProjectPath, YoutubeMusicSettings.DefaultCliProjectPath),
                CliArgs = Pick(task?.CliArgs, notif?.CliArgs, "--search"),
                ScanIntervalMinutes = task?.ScanIntervalMinutes ?? notif?.ScanIntervalMinutes ?? 1440,
                AuthCookie = Pick(task?.AuthCookie, notif?.AuthCookie, ""),
                MonitorAlbums = (task?.MonitorAlbums ?? notif?.MonitorAlbums) ?? true,
                Monitored = (task?.Monitored ?? notif?.Monitored) ?? true,
                QualityProfile = Pick(task?.QualityProfile, notif?.QualityProfile, ""),
                MetadataProfile = Pick(task?.MetadataProfile, notif?.MetadataProfile, ""),
                Playlists = Pick(task?.Playlists, notif?.Playlists, ""),
            };

            // A base install should work with just a cookie: fall back to the container
            // defaults even if the persisted definition carries an old/empty value.
            if (string.IsNullOrWhiteSpace(merged.PythonExecutable)
                || merged.PythonExecutable.Equals("python", StringComparison.OrdinalIgnoreCase)
                || merged.PythonExecutable.Equals("py", StringComparison.OrdinalIgnoreCase))
            {
                merged.PythonExecutable = YoutubeMusicSettings.DefaultPythonExecutable;
            }

            if (string.IsNullOrWhiteSpace(merged.CliProjectPath))
            {
                merged.CliProjectPath = YoutubeMusicSettings.DefaultCliProjectPath;
            }

            return merged;
        }

        private YoutubeMusicSettings? ResolveTaskSettings()
        {
            try
            {
                return _metadataFactory.Value.All()
                    .Where(d => d.Implementation == nameof(YoutubeMusicSyncTask))
                    .Select(d => d.Settings)
                    .OfType<YoutubeMusicSettings>()
                    .FirstOrDefault()
                    ?? Definition?.Settings as YoutubeMusicSettings;
            }
            catch (Exception ex)
            {
                _logger.Warn(ex, "[YTM] failed to read task settings");
                return Definition?.Settings as YoutubeMusicSettings;
            }
        }

        private YoutubeMusicSettings? ResolveNotificationSettings()
        {
            try
            {
                return _notificationFactory.Value.All()
                    .Where(d => d.Settings is YoutubeMusicSettings)
                    .Select(d => (YoutubeMusicSettings)d.Settings)
                    .FirstOrDefault();
            }
            catch (Exception ex)
            {
                _logger.Warn(ex, "[YTM] failed to read notification settings");
                return null;
            }
        }

        private static string Pick(string a, string b, string def)
            => !string.IsNullOrWhiteSpace(a) ? a : (!string.IsNullOrWhiteSpace(b) ? b : def);
    }
}