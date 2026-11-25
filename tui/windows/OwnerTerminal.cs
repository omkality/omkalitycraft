using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;

internal static class OwnerTerminal
{
    private static int Main()
    {
        bool first;
        using (var instance = new Mutex(true, @"Local\OmkalityCraftOwnerTui", out first))
        {
            if (!first)
                return Fail("Админка OmkalityCraft уже открыта.");
            return RunTerminal();
        }
    }

    private static int RunTerminal()
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
                " -o ClearAllForwardings=yes -o ForwardAgent=no -tt omkalitycraft-vps .local/bin/omk-tui-vps-invites", socket);
            start.EnvironmentVariables["TERM"] = "xterm-256color";
            var reports = Child(ssh, "-F " + Quote(config) +
                " -o ClearAllForwardings=yes -o ForwardAgent=no -o BatchMode=yes" +
                " -o ConnectTimeout=8 -o ServerAliveInterval=10 -o ServerAliveCountMax=2" +
                " -nT omkalitycraft-vps .local/bin/omk-tui-owner-stream", socket);
            var executable = typeof(OwnerTerminal).Assembly.Location;
            int exitCode;
            using (var download = new OwnerReports(reports, Path.GetDirectoryName(executable)))
                exitCode = Run(start);
            return exitCode == 0 ? 0 : Fail("SSH завершился с кодом " + exitCode + ".");
        }
        catch (Win32Exception error) { return Fail(error.Message); }
        catch (IOException error) { return Fail(error.Message); }
        catch (UnauthorizedAccessException error) { return Fail(error.Message); }
    }

    private sealed class OwnerReports : IDisposable
    {
        private const int MaxCrashBytes = 96 * 1024;
        private const string CrashPrefix = "CRASH ";
        private readonly ProcessStartInfo start;
        private readonly string folder;
        private readonly Thread worker;
        private readonly ManualResetEvent stop = new ManualResetEvent(false);
        private readonly object gate = new object();
        private Process active;
        private string saveError;

        internal OwnerReports(ProcessStartInfo start, string folder)
        {
            this.start = start;
            start.CreateNoWindow = true;
            start.RedirectStandardOutput = true;
            start.RedirectStandardError = true;
            this.folder = folder;
            worker = new Thread(Receive) { IsBackground = true };
            worker.SetApartmentState(ApartmentState.STA);
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
                                if (line.StartsWith("CLIP ", StringComparison.Ordinal))
                                {
                                    try { CopyInvitation(line.Substring(5)); }
                                    catch (ExternalException) { }
                                }
                                else if (line.Length != 0)
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
            bool crash = line.StartsWith(CrashPrefix, StringComparison.Ordinal);
            const int crashHeader = 6 + 32 + 1;
            string destination = Path.Combine(folder, "OmkalityCraft-Wipe.log");
            if (crash)
            {
                if (line.Length <= crashHeader || line.Length > crashHeader + MaxCrashBytes * 4 / 3 ||
                    line[crashHeader - 1] != ' ')
                    return;
                var id = line.Substring(CrashPrefix.Length, 32);
                if (!Regex.IsMatch(id, @"\A[0-9a-f]{32}\z"))
                    return;
                destination = Path.Combine(folder, "CrashReports", "client-crash-" + id + ".json");
                line = line.Substring(crashHeader);
            }
            else if (line.Length > 11000)
                return;
            byte[] data;
            try { data = Convert.FromBase64String(line); }
            catch (FormatException) { return; }
            if (crash
                ? data.Length < 2 || data.Length > MaxCrashBytes || data[0] != '{' || data[data.Length - 1] != '}'
                : data.Length > 8192 ||
                    !Encoding.UTF8.GetString(data).StartsWith("OmkalityCraft | World reset |", StringComparison.Ordinal))
                return;

            var temporary = destination + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try
            {
                if (crash)
                {
                    var directory = Directory.CreateDirectory(Path.GetDirectoryName(destination));
                    if ((directory.Attributes & FileAttributes.ReparsePoint) != 0)
                        throw new IOException("CrashReports is a redirected directory.");
                }
                using (var file = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write))
                    file.Write(data, 0, data.Length);
                if (File.Exists(destination))
                    File.Replace(temporary, destination, null);
                else
                    File.Move(temporary, destination);
                if (saveError == destination)
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
                Console.Error.WriteLine("Не удалось сохранить файл " + saveError);
        }
    }

    internal static bool CopyInvitation(string encoded)
    {
        if (encoded.Length > 172)
            return false;
        byte[] bytes;
        try { bytes = Convert.FromBase64String(encoded); }
        catch (FormatException) { return false; }
        if (bytes.Length == 0 || bytes.Length > 128)
            return false;
        foreach (byte symbol in bytes)
        {
            if (!(symbol >= 'A' && symbol <= 'Z' || symbol >= 'a' && symbol <= 'z' ||
                  symbol >= '0' && symbol <= '9' || symbol == '_' || symbol == '-'))
                return false;
        }
        Clipboard.SetText(Encoding.ASCII.GetString(bytes), TextDataFormat.UnicodeText);
        return true;
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
