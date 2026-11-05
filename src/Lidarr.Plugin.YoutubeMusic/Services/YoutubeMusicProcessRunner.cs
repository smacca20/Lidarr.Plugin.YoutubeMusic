using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Text;
using NLog;

namespace NzbDrone.Core.Plugins
{
    /// <summary>
    /// Executes the ytmusic-lidarr-sync Python CLI in-process of the schedule.
    /// Running the CLI keeps the (tested, Python-based) YT Music integration intact
    /// instead of re-implementing YT Music's internal API and Lidarr ingestion in C#.
    /// Writing tags: the CLI talks to Lidarr over the local API and uses its own config.ini.
    /// </summary>
    public class YoutubeMusicProcessRunner
    {
        private readonly Logger _logger;

        public YoutubeMusicProcessRunner(Logger logger)
        {
            _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        }

        /// <summary>The env var the CLI reads for an in-memory cookie (see ytmusic_lidarr_sync/auth.py).</summary>
        public const string AuthCookieEnvVar = "YTMLIDARR_AUTH_COOKIE";

        /// <summary>
        /// Runs the CLI synchronously, streaming output to the Lidarr log.
        /// Returns the process exit code (0 = success).
        /// </summary>
        public int Run(YoutubeMusicSettings settings, string? moduleArgs = null)
        {
            var py = (settings.PythonExecutable ?? "python").Trim();
            var args = (moduleArgs ?? settings.CliArgs ?? "--search");
            var workingDir = settings.CliProjectPath;

            _logger.Info("[YTM] starting sync: {0} -m ytmusic_lidarr_sync {1} (wd={2})", py, args, workingDir);

            var psi = new ProcessStartInfo
            {
                FileName = py,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                WorkingDirectory = workingDir,
            };

            psi.ArgumentList.Add("-m");
            psi.ArgumentList.Add("ytmusic_lidarr_sync");

            // CLI arguments are for the sync module, so they must come AFTER the module
            // name:  python3 -m ytmusic_lidarr_sync --search   (not before -m).
            foreach (var token in SplitArgs(args))
            {
                psi.ArgumentList.Add(token);
            }

            // Provide the auth cookie in memory only (ephemeral env var), never on disk.
            if (!string.IsNullOrEmpty(settings.AuthCookie))
            {
                psi.Environment[AuthCookieEnvVar] = settings.AuthCookie;
                _logger.Info("[YTM] passing YouTube Music cookie to sync via env (in memory)");
            }

            using var process = new Process { StartInfo = psi };
            try
            {
                if (!process.Start())
                {
                    _logger.Error("[YTM] failed to start process for {0}", py);
                    return -1;
                }
            }
            catch (Exception ex)
            {
                _logger.Error(ex, "[YTM] could not start Python: {0}", ex.Message);
                return -1;
            }

            // Read asynchronously so a chatty CLI cannot deadlock the pipes.
            var stdout = new StringBuilder();
            var stderr = new StringBuilder();
            process.OutputDataReceived += (_, e) => { if (e.Data != null) stdout.AppendLine(e.Data); };
            process.ErrorDataReceived += (_, e) => { if (e.Data != null) stderr.AppendLine(e.Data); };
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();

            process.WaitForExit();
            process.CancelOutputRead();
            process.CancelErrorRead();

            _logger.Info("[YTM] sync exited with code {0}", process.ExitCode);
            if (stdout.Length > 0)
            {
                _logger.Info("[YTM] stdout:\n{0}", stdout);
            }

            if (stderr.Length > 0)
            {
                _logger.Warn("[YTM] stderr:\n{0}", stderr);
            }

            return process.ExitCode;
        }

        /// <summary>Smallest correct-enough tokenizer for CLI args ("--search", "-p \"a b\"").</summary>
        private static IEnumerable<string> SplitArgs(string input)
        {
            var parts = new List<string>();
            var current = new StringBuilder();
            var inQuote = false;
            foreach (var ch in (input ?? string.Empty))
            {
                if (ch == '"')
                {
                    inQuote = !inQuote;
                }
                else if (char.IsWhiteSpace(ch) && !inQuote)
                {
                    if (current.Length > 0)
                    {
                        parts.Add(current.ToString());
                        current.Clear();
                    }
                }
                else
                {
                    current.Append(ch);
                }
            }

            if (current.Length > 0)
            {
                parts.Add(current.ToString());
            }

            return parts;
        }
    }
}