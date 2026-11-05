using System;
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
        public const string DefaultCliProjectPath = "/config/ytmusic-lidarr-sync";

        public YoutubeMusicSettings()
        {
            PythonExecutable = DefaultPythonExecutable;
            CliProjectPath = DefaultCliProjectPath;
            CliArgs = "--search";
            ScanIntervalMinutes = 1440;
            AuthCookie = "";
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