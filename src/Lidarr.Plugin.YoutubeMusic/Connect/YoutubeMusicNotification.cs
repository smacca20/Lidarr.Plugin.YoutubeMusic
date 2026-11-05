using System;
using FluentValidation.Results;
using NzbDrone.Core.Notifications;
using NzbDrone.Core.Plugins.Services;

namespace NzbDrone.Core.Plugins
{
    /// <summary>
    /// The "YouTube Music Sync" entry that appears in Settings &gt; Connect.
    /// This is the settings surface for the plugin. It captures the settings into
    /// <see cref="YoutubeMusicRunContext"/> so the scheduled command executor can
    /// read them; actual syncing is driven by the scheduled task.
    /// </summary>
    public class YoutubeMusicNotification : NotificationBase<YoutubeMusicSettings>
    {
        public override string Name => YoutubeMusicPlugin.DisplayName;

        public override string Link => YoutubeMusicPlugin.RepositoryUrl;

        public override ValidationResult Test()
        {
            YoutubeMusicRunContext.Current = Definition?.Settings as YoutubeMusicSettings ?? new YoutubeMusicSettings();
            return new ValidationResult();
        }
    }
}