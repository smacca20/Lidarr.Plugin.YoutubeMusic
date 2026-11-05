using System;
using NzbDrone.Core.Messaging.Commands;
using NzbDrone.Core.Plugins.Scheduling;
using NzbDrone.Core.Plugins.Services;

namespace NzbDrone.Core.Plugins
{
    /// <summary>
    /// The scheduled entry (Settings &gt; Metadata &gt; "YouTube Music Sync Scan").
    /// Registers <see cref="YoutubeMusicSyncCommand"/> on a configurable interval,
    /// giving in-app, UI-managed recurrence for the YT Music sync. Captures its
    /// settings so <see cref="YoutubeMusicSyncCommandExecutor"/> can run the CLI.
    /// </summary>
    public class YoutubeMusicSyncTask : ScheduledTaskBase<YoutubeMusicSettings>
    {
        public override string Name => "YouTube Music Sync Scan";

        public override Type CommandType => typeof(YoutubeMusicSyncCommand);

        public override int IntervalMinutes =>
            (Settings?.ScanIntervalMinutes ?? 0) < 60 ? 1440 : Settings!.ScanIntervalMinutes;

        public override CommandPriority Priority => CommandPriority.Normal;

        public YoutubeMusicSyncTask()
        {
            YoutubeMusicRunContext.Current = Settings ?? new YoutubeMusicSettings();
        }
    }
}