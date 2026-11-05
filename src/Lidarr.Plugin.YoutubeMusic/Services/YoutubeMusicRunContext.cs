namespace NzbDrone.Core.Plugins.Services
{
    /// <summary>
    /// Lightweight settings bridge between the provider definitions (Connect /
    /// scheduled Metadata entries) and the command executor that runs the Python CLI.
    /// Lidarr provider instances are created on demand, so the executor reads the
    /// last-known settings captured when a provider is instantiated/saved.
    /// For a single-user plugin this is a pragmatic, dependency-free approach.
    /// </summary>
    public static class YoutubeMusicRunContext
    {
        public static YoutubeMusicSettings Current { get; set; } = new YoutubeMusicSettings();
    }
}