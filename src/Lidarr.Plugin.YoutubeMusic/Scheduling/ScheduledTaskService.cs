using System;
using System.Collections.Generic;
using System.Linq;
using NLog;
using NzbDrone.Common.Cache;
using NzbDrone.Core.Extras.Metadata;
using NzbDrone.Core.Jobs;
using NzbDrone.Core.Messaging.Events;
using NzbDrone.Core.ThingiProvider.Events;

namespace NzbDrone.Core.Plugins.Scheduling
{
    /// <summary>
    /// Keeps the ScheduledTask table in sync with metadata providers that implement
    /// <see cref="IProvideScheduledTask"/>. Handles provider add/update/delete events
    /// to insert, update, or remove ScheduledTask rows. At startup the
    /// <see cref="ScheduledTaskServiceStarter"/> calls <see cref="CaptureExistingTasks"/>
    /// (before Lidarr's TaskManager purges non-built-in tasks) and then
    /// <see cref="InitializeTasks"/> (after) to re-register plugin tasks.
    /// Adapted from the pattern used by the UniqueSingles reference plugin.
    /// </summary>
    public class ScheduledTaskService :
        IHandle<ProviderAddedEvent<IMetadata>>,
        IHandle<ProviderUpdatedEvent<IMetadata>>,
        IHandle<ProviderDeletedEvent<IMetadata>>
    {
        private readonly IMetadataFactory _metadataFactory;
        private readonly IScheduledTaskRepository _scheduledTaskRepository;
        private readonly ICached<ScheduledTask> _cache;
        private readonly Logger _logger;

        private readonly HashSet<string> _registeredCommandTypes = new();
        private Dictionary<string, ScheduledTask> _capturedTasks = new();

        public ScheduledTaskService(
            IMetadataFactory metadataFactory,
            IScheduledTaskRepository scheduledTaskRepository,
            ICacheManager cacheManager,
            Logger logger)
        {
            _metadataFactory = metadataFactory ?? throw new ArgumentNullException(nameof(metadataFactory));
            _scheduledTaskRepository = scheduledTaskRepository ?? throw new ArgumentNullException(nameof(scheduledTaskRepository));
            _cache = cacheManager.GetCache<ScheduledTask>(typeof(TaskManager));
            _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        }

        public void Handle(ProviderAddedEvent<IMetadata> message)
        {
            if (message == null) throw new ArgumentNullException(nameof(message));
            var provider = _metadataFactory.GetInstance((MetadataDefinition)message.Definition);
            if (provider is IProvideScheduledTask sched)
            {
                if (!message.Definition.Enable)
                {
                    RemoveOrphanedTask(sched);
                    return;
                }

                RegisterOrUpdate(sched);
            }
        }

        public void Handle(ProviderUpdatedEvent<IMetadata> message)
        {
            if (message == null) throw new ArgumentNullException(nameof(message));
            var provider = _metadataFactory.GetInstance((MetadataDefinition)message.Definition);
            if (provider is IProvideScheduledTask sched)
            {
                if (!message.Definition.Enable)
                {
                    RemoveOrphanedTask(sched);
                    return;
                }

                RegisterOrUpdate(sched);
            }
        }

        public void Handle(ProviderDeletedEvent<IMetadata> message)
        {
            CleanupOrphanedTasks();
        }

        public void CaptureExistingTasks()
        {
            try
            {
                _capturedTasks = _scheduledTaskRepository.All()
                    .Where(t => !string.IsNullOrWhiteSpace(t.TypeName))
                    .GroupBy(t => t.TypeName)
                    .ToDictionary(g => g.Key, g => g.FirstOrDefault()!);
            }
            catch (Exception ex)
            {
                _logger.Warn(ex, "Failed to capture existing scheduled tasks");
                _capturedTasks = new Dictionary<string, ScheduledTask>();
            }
        }

        public void InitializeTasks()
        {
            foreach (var provider in _metadataFactory.Enabled().OfType<IProvideScheduledTask>())
            {
                RegisterOrUpdate(provider);
            }

            _capturedTasks = new Dictionary<string, ScheduledTask>();
            CleanupOrphanedTasks();
        }

        private void RegisterOrUpdate(IProvideScheduledTask provider)
        {
            var typeName = provider.CommandType.FullName!;
            var existing = FindScheduledTask(typeName);
            if (existing == null)
            {
                var task = new ScheduledTask
                {
                    TypeName = typeName,
                    Interval = provider.IntervalMinutes,
                    Priority = provider.Priority,
                };

                if (_capturedTasks.TryGetValue(typeName, out var captured))
                {
                    task.LastExecution = captured.LastExecution == default ? captured.LastStartTime : captured.LastExecution;
                    task.LastStartTime = captured.LastStartTime;
                    _capturedTasks.Remove(typeName);
                }
                else
                {
                    var initial = DateTime.UtcNow.AddMinutes(-provider.IntervalMinutes - 1);
                    task.LastExecution = initial;
                    task.LastStartTime = initial;
                }

                _scheduledTaskRepository.Insert(task);
                _cache.Set(typeName, task);
                _registeredCommandTypes.Add(typeName);
                _logger.Info("Registered plugin scheduled task {0} interval={1}min", typeName, provider.IntervalMinutes);
            }
            else
            {
                existing.Interval = provider.IntervalMinutes;
                existing.Priority = provider.Priority;
                _scheduledTaskRepository.Update(existing);
                _cache.Set(typeName, existing);
                _registeredCommandTypes.Add(typeName);
                _logger.Info("Updated plugin scheduled task {0} interval={1}min", typeName, provider.IntervalMinutes);
            }
        }

        private void RemoveOrphanedTask(IProvideScheduledTask provider)
        {
            var typeName = provider.CommandType.FullName!;
            var task = FindScheduledTask(typeName);
            if (task != null)
            {
                _scheduledTaskRepository.Delete(task.Id);
                _cache.Remove(typeName);
            }

            _registeredCommandTypes.Remove(typeName);
        }

        private void CleanupOrphanedTasks()
        {
            var active = _metadataFactory.Enabled()
                .OfType<IProvideScheduledTask>()
                .Select(p => p.CommandType.FullName!)
                .ToHashSet();

            var allKnown = _metadataFactory.GetAvailableProviders()
                .OfType<IProvideScheduledTask>()
                .Select(p => p.CommandType.FullName!);

            var orphans = _registeredCommandTypes.Union(allKnown).Where(t => !active.Contains(t));
            foreach (var typeName in orphans)
            {
                RemoveTask(typeName);
            }
        }

        private void RemoveTask(string typeName)
        {
            var task = FindScheduledTask(typeName);
            if (task != null)
            {
                _scheduledTaskRepository.Delete(task.Id);
                _logger.Info("Removed orphaned plugin scheduled task {0}", typeName);
            }

            _cache.Remove(typeName);
            _registeredCommandTypes.Remove(typeName);
        }

        private ScheduledTask? FindScheduledTask(string typeName)
        {
            try
            {
                return _scheduledTaskRepository.All().FirstOrDefault(t => t.TypeName == typeName);
            }
            catch (Exception ex)
            {
                _logger.Warn(ex, "Failed to query scheduled tasks");
                return null;
            }
        }
    }
}