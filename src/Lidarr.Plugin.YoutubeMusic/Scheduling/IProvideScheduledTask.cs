using System;
using NzbDrone.Core.Messaging.Commands;

namespace NzbDrone.Core.Plugins.Scheduling
{
    /// <summary>
    /// Marker interface for metadata providers that also provide a scheduled task.
    /// Implementations expose the command type to run, the interval in minutes,
    /// and the scheduling priority. <see cref="ScheduledTaskService"/> listens for
    /// provider lifecycle events and inserts/updates/removes ScheduledTask rows.
    /// </summary>
    public interface IProvideScheduledTask
    {
        Type CommandType { get; }
        int IntervalMinutes { get; }
        CommandPriority Priority { get; }
    }
}