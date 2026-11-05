using System;
using NLog;
using NzbDrone.Core.Lifecycle;
using NzbDrone.Core.Messaging.Events;

namespace NzbDrone.Core.Plugins.Scheduling
{
    /// <summary>
    /// Registers plugin scheduled tasks during Lidarr startup:
    ///  - On ApplicationStarting: capture existing rows before Lidarr's TaskManager
    ///    purges non-built-in tasks, so restart doesn't make the task fire immediately.
    ///  - On ApplicationStarted: (re)initialize plugin tasks after TaskManager ran.
    /// </summary>
    public class ScheduledTaskServiceStarter : IHandle<ApplicationStartingEvent>, IHandle<ApplicationStartedEvent>
    {
        private readonly ScheduledTaskService _scheduledTaskService;
        private readonly Logger _logger;

        public ScheduledTaskServiceStarter(ScheduledTaskService scheduledTaskService, Logger logger)
        {
            _scheduledTaskService = scheduledTaskService ?? throw new ArgumentNullException(nameof(scheduledTaskService));
            _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        }

        public void Handle(ApplicationStartingEvent message)
        {
            _logger.Debug("[YTM] ApplicationStarting: capturing scheduled task state");
            _scheduledTaskService.CaptureExistingTasks();
        }

        [EventHandleOrder(EventHandleOrder.Last)]
        public void Handle(ApplicationStartedEvent message)
        {
            _logger.Debug("[YTM] ApplicationStarted: initializing scheduled tasks");
            _scheduledTaskService.InitializeTasks();
        }
    }
}