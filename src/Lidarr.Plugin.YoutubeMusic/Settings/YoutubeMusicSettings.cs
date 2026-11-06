using System;
using System.IO;
using FluentValidation;
using NzbDrone.Core.Annotations;
using NzbDrone.Core.ThingiProvider;
using NzbDrone.Core.Validation;

namespace NzbDrone.Core.Plugins
{
    /// <summary>
    /// Shared settings for the "YouTube Music Sync" plugin.
    /// The plugin schedules the proven Python CLI (see Services/YoutubeMusicProcessRunner)
    /// to read YT Music likes/playlists and add the matching artists/albums to Lidarr.
    /// </summary>
    public class YoutubeMusicSettings : IProviderConfig
    {
        /// <summary>Defaults for a container install, so a base setup only needs the cookie.</summary>
        public const string DefaultPythonExecutable = "/usr/bin/python3";
        public const string MountedProjectPath = "/config/ytmusic-lidarr-sync";
        public const string BakedProjectPath = "/app/sync";

        /// <summary>Pick whichever sync-project path actually exists on this host.</summary>
        public static string DefaultCliProjectPath =>
            Directory.Exists(Path.Combine(BakedProjectPath, "ytmusic_lidarr_sync")) ? BakedProjectPath
            : Directory.Exists(Path.Combine(MountedProjectPath, "ytmusic_lidarr_sync")) ? MountedProjectPath
            : MountedProjectPath;

        public YoutubeMusicSettings()
        {
            PythonExecutable = DefaultPythonExecutable;
            CliProjectPath = DefaultCliProjectPath;
            CliArgs = "--search";
            ScanIntervalMinutes = 1440;
            AuthCookie = "";
            MonitorAlbums = true;
            Monitored = true;
            QualityProfile = "";   // blank = auto-detect (prefers Lossless)
            MetadataProfile = "";  // blank = auto-detect (prefers Standard)
            Playlists = "";
        }

        [FieldDefinition(0, Label = "Python executable", Type = FieldType.Textbox,
            HelpText = "Command to start Python on the Lidarr host (e.g. 'python', 'py -3', or an absolute path).")]
        public string PythonExecutable { get; set; }

        [FieldDefinition(1, Label = "Sync project path", Type = FieldType.Textbox,
            HelpText = "Absolute path to the ytmusic-lidarr-sync project folder that contains config.ini and the package. Required.")]
        public string CliProjectPath { get; set; }

        [FieldDefinition(2, Label = "CLI arguments", Type = FieldType.Textbox,
            HelpText = "Arguments passed to 'python -m ytmusic_lidarr_sync'. Default '--search' adds missing artists and triggers album searches.")]
        public string CliArgs { get; set; }

        [FieldDefinition(3, Label = "Scan interval (minutes)", Type = FieldType.Number,
            HelpText = "How often to run the sync. Minimum 60 minutes. Only read from the scheduled entry (Settings > Metadata).")]
        public int ScanIntervalMinutes { get; set; }

        [FieldDefinition(4, Label = "YouTube Music cookie (auth)", Type = FieldType.Password,
            HelpText = "Optional. Open https://music.youtube.com in a browser, sign in, then copy the full 'Cookie' header value (DevTools > Network > any request > Request Headers > Cookie) and paste it here. It is held in memory and passed to the sync process via an environment variable - never written to disk. Leave empty to use headers_file instead.")]
        public string AuthCookie { get; set; }

        [FieldDefinition(5, Label = "Monitor matched albums & singles", Type = FieldType.Checkbox,
            HelpText = "Monitor ONLY the albums/singles that matched a liked track (not the artist's whole discography). Default ON. Disable to add artists while leaving albums unmonitored.")]
        public bool MonitorAlbums { get; set; } = true;

        [FieldDefinition(6, Label = "Monitored (default for new artists)", Type = FieldType.Checkbox,
            HelpText = "Whether newly added artists are set as Monitored. Default ON.")]
        public bool Monitored { get; set; } = true;

        [FieldDefinition(7, Label = "Quality Profile (name)", Type = FieldType.Textbox,
            HelpText = "Lidarr quality profile by NAME for added artists (Settings > Profiles > Quality), e.g. Lossless / Standard / Any. Leave blank for auto-detect (prefers Lossless).")]
        public string QualityProfile { get; set; } = "";

        [FieldDefinition(8, Label = "Metadata Profile (name)", Type = FieldType.Textbox,
            HelpText = "Lidarr metadata profile by NAME for added artists (Settings > Profiles > Metadata), e.g. Standard / None / Albums and Singles. Leave blank for auto-detect (prefers Standard).")]
        public string MetadataProfile { get; set; } = "";

        [FieldDefinition(9, Label = "Playlists to sync (comma-separated names)", Type = FieldType.Textbox,
            HelpText = "Optional. Comma-separated names of YOUR YouTube Music playlists to sync (resolved from your library). Leave empty to sync liked songs (or a URL/ID via CLI arguments). Use --limit 0 (via CLI arguments) to sync each entire playlist.")]
        public string Playlists { get; set; } = "";

        public NzbDroneValidationResult Validate()
        {
            return new NzbDroneValidationResult(new YoutubeMusicSettingsValidator().Validate(this));
        }
    }

    public class YoutubeMusicSettingsValidator : AbstractValidator<YoutubeMusicSettings>
    {
        public YoutubeMusicSettingsValidator()
        {
            RuleFor(c => c.PythonExecutable).NotEmpty()
                .WithMessage("Python executable path is required");
            RuleFor(c => c.CliProjectPath).NotEmpty()
                .WithMessage("Sync project path is required");
            RuleFor(c => c.ScanIntervalMinutes).GreaterThanOrEqualTo(60)
                .WithMessage("Scan interval must be at least 60 minutes");
        }
    }
}