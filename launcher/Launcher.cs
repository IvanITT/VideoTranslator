// Spanish Dubbing Studio - local launcher (tray application)
//
// Starts the local FastAPI server with the project's virtual environment,
// waits until the API answers, opens the browser and keeps an icon in the
// notification area to stop the server and quit cleanly.
//
// Command line:
//   "Spanish Dubbing Studio.exe"               tray app, starts server, opens browser
//   "Spanish Dubbing Studio.exe" --no-browser  tray app, does not open the browser
//   "Spanish Dubbing Studio.exe" --stop        stops the local server and exits
//   "Spanish Dubbing Studio.exe" --status      exit code 0 when the server is up
//
// Built with launcher\build.ps1 (csc from the .NET Framework).

using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Windows.Forms;

[assembly: System.Reflection.AssemblyTitle("Spanish Dubbing Studio")]
[assembly: System.Reflection.AssemblyProduct("Spanish Dubbing Studio")]
[assembly: System.Reflection.AssemblyDescription("Local launcher for Spanish Dubbing Studio")]
[assembly: System.Reflection.AssemblyCompany("Spanish Dubbing Studio")]
[assembly: System.Reflection.AssemblyVersion("1.0.0.0")]
[assembly: System.Reflection.AssemblyFileVersion("1.0.0.0")]

namespace SpanishDubbingStudio
{
    internal static class Program
    {
        internal const string AppName = "Spanish Dubbing Studio";
        private const string MutexName = @"Local\SpanishDubbingStudio.Launcher";

        internal static string Root;
        internal static string Backend;
        internal static string Python;
        internal static string LogDir;
        internal static string LogFile;
        internal static int Port;

        [STAThread]
        private static int Main(string[] args)
        {
            Root = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
            Backend = Path.Combine(Root, "backend");
            Python = Path.Combine(Root, @".venv\Scripts\python.exe");
            LogDir = Path.Combine(Root, @"storage\logs");
            LogFile = Path.Combine(LogDir, "server.log");
            Port = ReadPort();

            try { Directory.CreateDirectory(LogDir); } catch { }

            if (Has(args, "--status")) return IsHealthy() ? 0 : 1;
            if (Has(args, "--stop")) { StopServer(true); return 0; }
            bool noBrowser = Has(args, "--no-browser");

            if (!File.Exists(Python) || !Directory.Exists(Backend))
            {
                MessageBox.Show(
                    "No se encontró el entorno de Python de la aplicación.\n\n" +
                    "Ejecuta primero scripts\\setup.ps1 desde:\n" + Root +
                    "\n\nDespués vuelve a abrir este acceso directo.",
                    AppName, MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 2;
            }

            bool created;
            using (var mutex = new Mutex(true, MutexName, out created))
            {
                if (!created)
                {
                    // Another launcher is already running: just show the app.
                    if (!noBrowser) OpenBrowser();
                    return 0;
                }
                try
                {
                    Application.EnableVisualStyles();
                    Application.SetCompatibleTextRenderingDefault(false);
                    Application.Run(new TrayApp(noBrowser));
                }
                finally
                {
                    mutex.ReleaseMutex();
                }
            }
            return 0;
        }

        internal static string Url { get { return "http://127.0.0.1:" + Port; } }

        internal static int ReadPort()
        {
            int port;
            if (int.TryParse(Environment.GetEnvironmentVariable("VTS_PORT"), out port)
                && port > 0 && port < 65536)
            {
                return port;
            }
            return 8765;
        }

        internal static bool Has(string[] args, string flag)
        {
            foreach (var value in args)
            {
                if (string.Equals(value, flag, StringComparison.OrdinalIgnoreCase)) return true;
            }
            return false;
        }

        internal static bool IsHealthy()
        {
            try
            {
                var request = (HttpWebRequest)WebRequest.Create(Url + "/api/health");
                request.Proxy = null;
                request.Timeout = 1500;
                request.ReadWriteTimeout = 1500;
                request.KeepAlive = false;
                using (var response = (HttpWebResponse)request.GetResponse())
                using (var reader = new StreamReader(response.GetResponseStream(), Encoding.UTF8))
                {
                    return reader.ReadToEnd().IndexOf("offline_ready", StringComparison.Ordinal) >= 0;
                }
            }
            catch
            {
                return false;
            }
        }

        internal static void OpenBrowser()
        {
            try
            {
                Process.Start(new ProcessStartInfo(Url) { UseShellExecute = true });
            }
            catch
            {
                // No default browser: nothing else to do, the URL is in the menu.
            }
        }

        private static readonly object LogLock = new object();

        internal static void AppendLog(string line)
        {
            try
            {
                lock (LogLock)
                {
                    var info = new FileInfo(LogFile);
                    if (info.Exists && info.Length > 5 * 1024 * 1024)
                    {
                        File.WriteAllText(LogFile, "--- registro reiniciado ---" + Environment.NewLine, Encoding.UTF8);
                    }
                    File.AppendAllText(
                        LogFile,
                        DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  " + line + Environment.NewLine,
                        Encoding.UTF8);
                }
            }
            catch
            {
                // Logging is best effort.
            }
        }

        internal static string PidFile
        {
            get { return Path.Combine(LogDir, "server.pid"); }
        }

        internal static void WritePid(int pid)
        {
            try { File.WriteAllText(PidFile, pid.ToString()); } catch { }
        }

        internal static bool IsOurs(int pid)
        {
            try
            {
                using (var process = Process.GetProcessById(pid))
                {
                    string path;
                    try { path = process.MainModule.FileName; }
                    catch { return false; }
                    if (string.IsNullOrEmpty(path)) return false;
                    return string.Equals(
                        Path.GetFullPath(path).ToLowerInvariant(),
                        Path.GetFullPath(Python).ToLowerInvariant());
                }
            }
            catch
            {
                return false;
            }
        }

        internal static int FindListenerPid()
        {
            try
            {
                var psi = new ProcessStartInfo("powershell.exe",
                    "-NoProfile -NonInteractive -Command \"(Get-NetTCPConnection -LocalPort " +
                    Port + " -State Listen -ErrorAction SilentlyContinue | " +
                    "Select-Object -First 1 -ExpandProperty OwningProcess)\"")
                {
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                };
                using (var process = Process.Start(psi))
                {
                    string output = process.StandardOutput.ReadToEnd().Trim();
                    process.WaitForExit(5000);
                    int pid;
                    if (int.TryParse(output, out pid)) return pid;
                }
            }
            catch
            {
                // Fall through.
            }
            return 0;
        }

        internal static bool KillTree(int pid)
        {
            try
            {
                var psi = new ProcessStartInfo("taskkill.exe", "/PID " + pid + " /T /F")
                {
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                };
                using (var process = Process.Start(psi))
                {
                    process.WaitForExit(8000);
                    return process.ExitCode == 0;
                }
            }
            catch
            {
                return false;
            }
        }

        internal static bool PortOpen()
        {
            try
            {
                using (var client = new TcpClient())
                {
                    var async = client.BeginConnect("127.0.0.1", Port, null, null);
                    if (!async.AsyncWaitHandle.WaitOne(400)) return false;
                    client.EndConnect(async);
                    return true;
                }
            }
            catch
            {
                return false;
            }
        }

        internal static bool StopServer(bool silent)
        {
            int pidFromFile = 0;
            try
            {
                if (File.Exists(PidFile)) int.TryParse(File.ReadAllText(PidFile).Trim(), out pidFromFile);
            }
            catch { }

            int listener = FindListenerPid();
            bool killed = false;

            if (pidFromFile > 0 && IsOurs(pidFromFile))
            {
                killed = KillTree(pidFromFile) || killed;
            }
            if (listener > 0 && listener != pidFromFile && IsOurs(listener))
            {
                killed = KillTree(listener) || killed;
            }

            if (killed)
            {
                // taskkill returns before the socket is released: wait for the port.
                for (int i = 0; i < 60; i++)
                {
                    if (!PortOpen()) break;
                    Thread.Sleep(250);
                }
            }
            try { if (File.Exists(PidFile)) File.Delete(PidFile); } catch { }

            AppendLog(killed
                ? "Servidor detenido (pid " + pidFromFile + ", escucha " + listener + ")."
                : "No se encontró un servidor propio en ejecución.");
            return killed;
        }
    }

    internal sealed class TrayApp : ApplicationContext
    {
        private readonly NotifyIcon _tray;
        private readonly System.Windows.Forms.Timer _timer;
        private readonly ToolStripMenuItem _statusItem;
        private readonly ToolStripMenuItem _startItem;
        private readonly ToolStripMenuItem _stopItem;
        private readonly bool _noBrowser;
        private Process _server;
        private bool _everUp;
        private bool _warnedDown;
        private bool _stopping;
        private DateTime _startedAt;

        public TrayApp(bool noBrowser)
        {
            _noBrowser = noBrowser;

            var menu = new ContextMenuStrip();
            _statusItem = new ToolStripMenuItem("Iniciando…");
            _statusItem.Enabled = false;

            var open = new ToolStripMenuItem("Abrir estudio", null, delegate { Program.OpenBrowser(); });
            open.Font = new Font(open.Font, FontStyle.Bold);
            open.ShortcutKeyDisplayString = "doble clic";

            menu.Items.Add(_statusItem);
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add(open);
            menu.Items.Add(new ToolStripMenuItem("Abrir carpeta de videos", null, delegate { OpenExports(); }));
            menu.Items.Add(new ToolStripMenuItem("Ver registro", null, delegate { OpenLog(); }));
            menu.Items.Add(new ToolStripSeparator());
            _startItem = new ToolStripMenuItem("Iniciar servidor", null, delegate { StartFromMenu(); });
            _startItem.Enabled = false;
            _stopItem = new ToolStripMenuItem("Detener servidor", null, delegate { StopFromMenu(); });
            menu.Items.Add(_startItem);
            menu.Items.Add(_stopItem);
            menu.Items.Add(new ToolStripMenuItem("Salir", null, delegate { ExitApp(); }));

            _tray = new NotifyIcon();
            _tray.Icon = LoadIcon();
            _tray.Text = Program.AppName;
            _tray.ContextMenuStrip = menu;
            _tray.Visible = true;
            _tray.DoubleClick += delegate { Program.OpenBrowser(); };
            _tray.BalloonTipClicked += delegate { Program.OpenBrowser(); };

            if (Program.IsHealthy())
            {
                _everUp = true;
                SetStatus("Activo · " + Program.Url);
                _stopItem.Enabled = true;
            }
            else
            {
                _stopItem.Enabled = false;
                StartServer();
            }

            _timer = new System.Windows.Forms.Timer();
            _timer.Interval = 2000;
            _timer.Tick += delegate { Poll(); };
            _timer.Start();
        }

        private void StartServer()
        {
            try
            {
                if (_server != null)
                {
                    try { _server.Dispose(); } catch { }
                    _server = null;
                }
                _startedAt = DateTime.Now;
                _startItem.Enabled = false;
                _stopItem.Enabled = false;

                var psi = new ProcessStartInfo(
                    Program.Python,
                    "-m uvicorn app.main:app --host 127.0.0.1 --port " + Program.Port)
                {
                    WorkingDirectory = Program.Backend,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    StandardOutputEncoding = Encoding.UTF8,
                    StandardErrorEncoding = Encoding.UTF8,
                };
                psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
                psi.EnvironmentVariables["VTS_HOST"] = "127.0.0.1";
                psi.EnvironmentVariables["VTS_PORT"] = Program.Port.ToString();

                var process = new Process();
                process.StartInfo = psi;
                process.EnableRaisingEvents = true;
                process.OutputDataReceived += delegate(object sender, DataReceivedEventArgs e)
                {
                    if (e.Data != null) Program.AppendLog(e.Data);
                };
                process.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs e)
                {
                    if (e.Data != null) Program.AppendLog(e.Data);
                };
                process.Start();
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();
                _server = process;
                Program.WritePid(process.Id);
                SetStatus("Iniciando servidor…");
                Program.AppendLog("Lanzador: servidor iniciado (pid " + process.Id + ").");
            }
            catch (Exception ex)
            {
                Program.AppendLog("Lanzador: error al iniciar el servidor: " + ex.Message);
                MessageBox.Show(
                    "No se pudo iniciar el servidor local.\n\n" + ex.Message +
                    "\n\nRevisa el registro en:\n" + Program.LogFile,
                    Program.AppName, MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private void Poll()
        {
            if (_stopping) return;

            bool up = Program.IsHealthy();
            if (up)
            {
                _startItem.Enabled = false;
                _stopItem.Enabled = true;
                if (!_everUp)
                {
                    _everUp = true;
                    _warnedDown = false;
                    SetStatus("Activo · " + Program.Url);
                    Program.AppendLog("Lanzador: servidor listo en " + Program.Url);
                    _tray.ShowBalloonTip(
                        4000, Program.AppName,
                        "Listo en " + Program.Url +
                        "\nDoble clic en este icono para abrir la aplicación.",
                        ToolTipIcon.Info);
                    if (!_noBrowser) Program.OpenBrowser();
                }
                return;
            }

            if (_everUp)
            {
                _everUp = false;
                SetStatus("Servidor detenido");
                _startItem.Enabled = true;
                _stopItem.Enabled = false;
                if (!_warnedDown)
                {
                    _warnedDown = true;
                    _tray.ShowBalloonTip(
                        5000, Program.AppName,
                        "El servidor se detuvo. Usa «Iniciar servidor» o vuelve a abrir la aplicación.",
                        ToolTipIcon.Warning);
                }
                return;
            }

            if (_server != null)
            {
                bool exited = false;
                try { exited = _server.HasExited; } catch { }
                if (exited || (DateTime.Now - _startedAt).TotalSeconds > 150)
                {
                    SetStatus("No se pudo iniciar · revisa el registro");
                    _startItem.Enabled = true;
                    _stopItem.Enabled = false;
                }
            }
        }

        private void StartFromMenu()
        {
            if (Program.IsHealthy())
            {
                Program.OpenBrowser();
                return;
            }
            _warnedDown = false;
            StartServer();
        }

        private void SetStatus(string text)
        {
            _statusItem.Text = text;
            try { _tray.Text = text.Length > 60 ? text.Substring(0, 60) : text; } catch { }
        }

        private void OpenExports()
        {
            try
            {
                string folder = Path.Combine(Program.Root, @"storage\exports");
                Directory.CreateDirectory(folder);
                Process.Start(new ProcessStartInfo(folder) { UseShellExecute = true });
            }
            catch (Exception ex)
            {
                MessageBox.Show("No se pudo abrir la carpeta.\n\n" + ex.Message,
                    Program.AppName, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }

        private void OpenLog()
        {
            try
            {
                if (!File.Exists(Program.LogFile))
                {
                    File.WriteAllText(Program.LogFile, "Todavía no hay actividad." + Environment.NewLine, Encoding.UTF8);
                }
                Process.Start("notepad.exe", Program.LogFile);
            }
            catch (Exception ex)
            {
                MessageBox.Show("No se pudo abrir el registro.\n\n" + ex.Message,
                    Program.AppName, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }

        private void StopFromMenu()
        {
            if (MessageBox.Show(
                    "¿Detener el servidor local?\n\nLos trabajos en curso se interrumpirán, " +
                    "pero podrás reanudarlos al volver a abrir la aplicación.",
                    Program.AppName, MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
            {
                return;
            }

            _stopping = true;
            bool stopped = Program.StopServer(false);
            if (_server != null)
            {
                try { _server.Dispose(); } catch { }
                _server = null;
            }
            _everUp = false;
            SetStatus("Servidor detenido");
            _startItem.Enabled = true;
            _stopItem.Enabled = false;
            _tray.ShowBalloonTip(
                3000, Program.AppName,
                stopped ? "Servidor detenido." : "El servidor ya estaba detenido.",
                stopped ? ToolTipIcon.Info : ToolTipIcon.Warning);
            _stopping = false;
        }

        private void ExitApp()
        {
            if (MessageBox.Show(
                    "¿Cerrar la aplicación y detener el servidor local?",
                    Program.AppName, MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
            {
                return;
            }

            _timer.Stop();
            _tray.Visible = false;
            try { Program.StopServer(true); } catch { }
            if (_server != null)
            {
                try { _server.Dispose(); } catch { }
                _server = null;
            }
            _tray.Dispose();
            ExitThread();
        }

        private static Icon LoadIcon()
        {
            try
            {
                var icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
                if (icon != null) return icon;
            }
            catch { }
            return SystemIcons.Application;
        }
    }
}
