using System;
using FluentValidation.Results;
using NzbDrone.Core.Notifications;

namespace NzbDrone.Core.Plugins
{
    /// <summary>
    /// The optional "YouTube Music Sync" entry under Settings &gt; Connect. This exists
    /// primarily as a settings surface and a Test button; the actual run is driven by
    /// the scheduled entry under Settings &gt; Metadata (YoutubeMusicSyncTask).
    /// </summary>
    public class YoutubeMusicNotification : NotificationBase<YoutubeMusicSettings>
    {
        public override string Name => YoutubeMusicPlugin.DisplayName;

        public override string Link => YoutubeMusicPlugin.RepositoryUrl;

        public override ValidationResult Test()
        {
            return new ValidationResult();
        }
    }
}