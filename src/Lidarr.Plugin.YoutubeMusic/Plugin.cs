namespace NzbDrone.Core.Plugins
{
    /// <summary>
    /// Plugin entry point. This is what makes the assembly discoverable from the
    /// System &gt; Plugins UI (which loads plugins from GitHub Releases of this repo).
    /// </summary>
    public class YoutubeMusicPlugin : Plugin
    {
        public const string DisplayName = "YouTube Music Sync";
        public const string RepositoryUrl = "https://github.com/smacca20/Lidarr.Plugin.YoutubeMusic";

        public override string Name => DisplayName;
        public override string Owner => "smacca20";
        public override string GithubUrl => RepositoryUrl;
    }
}