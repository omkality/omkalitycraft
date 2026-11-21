using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;

internal static class OwnerTerminal
{
    private static int Main()
    {
        var profile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var sshDirectory = Path.Combine(profile, ".ssh");
        var config = Path.Combine(sshDirectory, "omkalitycraft_vps.conf");
        var nativeSsh = Path.Combine(Environment.SystemDirectory, "OpenSSH", "ssh.exe");
        var gitTools = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Git", "usr", "bin");

        ResizeConsole();
        try
        {
            if (!File.Exists(config))
                return Fail("Не найдены настройки SSH для OmkalityCraft.");

            var ssh = Path.Combine(gitTools, "ssh.exe");
            var socket = PrepareAgent(gitTools, sshDirectory);
            if (socket == null)
                ssh = nativeSsh;

            var start = Child(ssh, "-F " + Quote(config) +
                " -o ClearAllForwardings=yes -o ForwardAgent=no -tt omkalitycraft-vps .local/bin/omk-tui-vps-restrictions", socket);
            start.EnvironmentVariables["TERM"] = "xterm-256color";
            var reports = Child(ssh, "-F " + Quote(config) +
                " -o ClearAllForwardings=yes -o ForwardAgent=no -o BatchMode=yes" +
                " -o ConnectTimeout=8 -o ServerAliveInterval=10 -o ServerAliveCountMax=2" +
                " -nT omkalitycraft-vps .local/bin/omk-tui-report-stream", socket);
            var executable = typeof(OwnerTerminal).Assembly.Location;
            int exitCode;
            using (var download = new WipeReports(reports, Path.GetDirectoryName(executable)))
                exitCode = Run(start);
            return exitCode == 0 ? 0 : Fail("SSH завершился с кодом " + exitCode + ".");
        }
        catch (Win32Exception error) { return Fail(error.Message); }
        catch (IOException error) { return Fail(error.Message); }
        catch (UnauthorizedAccessException error) { return Fail(error.Message); }
    }

    private sealed class WipeReports : IDisposable
    {
        private readonly ProcessStartInfo start;
        private readonly string destination;
        private readonly Thread worker;
        private readonly ManualResetEvent stop = new ManualResetEvent(false);
        private readonly object gate = new object();
        private Process active;
        private string saveError;

        internal WipeReports(ProcessStartInfo start, string folder)
        {
            this.start = start;
            start.CreateNoWindow = true;
            start.RedirectStandardOutput = true;
            start.RedirectStandardError = true;
            destination = Path.Combine(folder, "OmkalityCraft-Wipe.log");
            worker = new Thread(Receive) { IsBackground = true };
            worker.Start();
        }

        private void Receive()
        {
            while (!stop.WaitOne(0))
            {
                try
                {
                    using (var process = new Process { StartInfo = start })
                    {
                        lock (gate)
                        {
                            if (stop.WaitOne(0))
                                return;
                            process.Start();
                            active = process;
                        }
                        try
                        {
                            process.ErrorDataReceived += delegate {};
                            process.BeginErrorReadLine();
                            string line;
                            while (!stop.WaitOne(0) && (line = process.StandardOutput.ReadLine()) != null)
                            {
                                if (line.Length != 0)
                                    Save(line);
                            }
                        }
                        finally
                        {
                            lock (gate)
                            {
                                Kill(process);
                                active = null;
                            }
                        }
                    }
                }
                catch (IOException) { }
                catch (Win32Exception) { }
                if (stop.WaitOne(3000))
                    return;
            }
        }

        private void Save(string line)
        {
            if (line.Length > 11000)
                return;
            byte[] data;
            try { data = Convert.FromBase64String(line); }
            catch (FormatException) { return; }
            if (data.Length > 8192 ||
                !Encoding.UTF8.GetString(data).StartsWith("OmkalityCraft | World reset |", StringComparison.Ordinal))
                return;

            var temporary = destination + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try
            {
                using (var file = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write))
                    file.Write(data, 0, data.Length);
                if (File.Exists(destination))
                    File.Replace(temporary, destination, null);
                else
                    File.Move(temporary, destination);
                saveError = null;
            }
            catch (IOException) { saveError = destination; }
            catch (UnauthorizedAccessException) { saveError = destination; }
            finally
            {
                try { File.Delete(temporary); }
                catch (IOException) { }
                catch (UnauthorizedAccessException) { }
            }
        }

        private static void Kill(Process process)
        {
            try { if (!process.HasExited) process.Kill(); }
            catch (Win32Exception) { }
            catch (InvalidOperationException) { }
        }

        public void Dispose()
        {
            stop.Set();
            lock (gate)
                if (active != null)
                    Kill(active);
            if (worker.Join(3000))
                stop.Dispose();
            if (saveError != null)
                Console.Error.WriteLine("Не удалось сохранить журнал: " + saveError);
        }
    }

    private static string PrepareAgent(string gitTools, string sshDirectory)
    {
        var agent = Path.Combine(gitTools, "ssh-agent.exe");
        var add = Path.Combine(gitTools, "ssh-add.exe");
        var key = Path.Combine(sshDirectory, "id_ed25519_omkalitycraft_vps");
        if (!File.Exists(agent) || !File.Exists(add) || !File.Exists(Path.Combine(gitTools, "ssh.exe")) ||
            !File.Exists(key) || !File.Exists(key + ".pub"))
            return null;

        var socket = Path.Combine(sshDirectory, "omk-tui-agent.sock").Replace('\\', '/');
        using (var gate = new Mutex(false, @"Local\OmkalityCraftOwnerTuiAgent"))
        {
            var acquired = false;
            try
            {
                try { acquired = gate.WaitOne(TimeSpan.FromSeconds(90)); }
                catch (AbandonedMutexException) { acquired = true; }
                if (!acquired)
                    return null;

                if (Probe(add, "-l", socket) == 2)
                {
                    if (File.Exists(socket))
                        File.Delete(socket);
                    var start = Child(agent, "-D -a " + Quote(socket) + " -t 2h", socket);
                    start.CreateNoWindow = true;
                    start.RedirectStandardInput = true;
                    start.RedirectStandardOutput = true;
                    start.RedirectStandardError = true;
                    using (var process = Process.Start(start))
                    {
                        for (int i = 0; i < 20; i++)
                        {
                            if (Probe(add, "-l", socket) != 2)
                                break;
                            if (process.HasExited)
                                return null;
                            Thread.Sleep(100);
                        }
                    }
                }

                if (Probe(add, "-T " + Quote(key + ".pub"), socket) == 0)
                    return socket;
                if (Probe(add, "-l", socket) == 2)
                    return null;
                return Run(Child(add, "-t 2h " + Quote(key), socket)) == 0 ? socket : null;
            }
            finally
            {
                if (acquired)
                    gate.ReleaseMutex();
            }
        }
    }

    private static int Probe(string exe, string args, string socket)
    {
        var start = Child(exe, args, socket);
        start.CreateNoWindow = true;
        start.RedirectStandardOutput = true;
        start.RedirectStandardError = true;
        return Run(start);
    }

    private static ProcessStartInfo Child(string exe, string args, string socket)
    {
        var start = new ProcessStartInfo(exe, args) { UseShellExecute = false };
        start.EnvironmentVariables.Remove("SSH_AGENT_PID");
        if (socket == null)
            start.EnvironmentVariables.Remove("SSH_AUTH_SOCK");
        else
            start.EnvironmentVariables["SSH_AUTH_SOCK"] = socket;
        return start;
    }

    private static int Run(ProcessStartInfo start)
    {
        using (var process = Process.Start(start))
        {
            process.WaitForExit();
            return process.ExitCode;
        }
    }

    private static string Quote(string argument) { return "\"" + argument + "\""; }

    private static void ResizeConsole()
    {
        try
        {
            if (Console.IsOutputRedirected)
                return;
            Console.Title = "OmkalityCraft - Owner TUI";
            int width = Math.Max(Console.WindowWidth, Math.Min(136, Console.LargestWindowWidth));
            int height = Math.Max(Console.WindowHeight, Math.Min(35, Console.LargestWindowHeight));
            Console.SetBufferSize(Math.Max(width, Console.BufferWidth), Math.Max(height, Console.BufferHeight));
            Console.SetWindowSize(width, height);
        }
        catch (IOException) { }
        catch (ArgumentOutOfRangeException) { }
        catch (PlatformNotSupportedException) { }
    }

    private static int Fail(string message)
    {
        Console.Error.WriteLine(message);
        if (!Console.IsInputRedirected)
        {
            Console.Error.WriteLine("Нажми Enter, чтобы закрыть окно.");
            Console.ReadLine();
        }
        return 1;
    }
}
