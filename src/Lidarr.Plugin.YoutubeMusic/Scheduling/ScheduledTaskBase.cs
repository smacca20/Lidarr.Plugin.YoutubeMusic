using System;
using System.Collections.Generic;
using NzbDrone.Core.Extras.Metadata;
using NzbDrone.Core.Extras.Metadata.Files;
using NzbDrone.Core.MediaFiles;
using NzbDrone.Core.Messaging.Commands;
using NzbDrone.Core.Music;
using NzbDrone.Core.ThingiProvider;

namespace NzbDrone.Core.Plugins.Scheduling
{
    /// <summary>
    /// Base class for metadata providers that also register a scheduled task.
    /// Inherits <see cref="MetadataBase{TSettings}"/> so it appears in Lidarr's
    /// Settings &gt; Metadata section, and implements <see cref="IProvideScheduledTask"/>
    /// so <see cref="ScheduledTaskService"/> schedules the command on an interval.
    /// The metadata methods are no-ops: this provider exists for scheduling, not metadata.
    /// </summary>
    public abstract class ScheduledTaskBase<TSettings> : MetadataBase<TSettings>, IProvideScheduledTask
        where TSettings : IProviderConfig, new()
    {
        public abstract Type CommandType { get; }
        public abstract int IntervalMinutes { get; }
        public abstract CommandPriority Priority { get; }

        public override MetadataFile FindMetadataFile(Artist artist, string path) => null!;
        public override MetadataFileResult ArtistMetadata(Artist artist) => null!;
        public override MetadataFileResult AlbumMetadata(Artist artist, Album album, string albumPath) => null!;
        public override MetadataFileResult TrackMetadata(Artist artist, TrackFile trackFile) => null!;
        public override List<ImageFileResult> ArtistImages(Artist artist) => new();
        public override List<ImageFileResult> AlbumImages(Artist artist, Album album, string albumPath) => new();
        public override List<ImageFileResult> TrackImages(Artist artist, TrackFile trackFile) => new();
    }
}