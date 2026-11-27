using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace KinoShopLauncher
{
    static class Program
    {
        [DllImport("shell32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        static extern int SetCurrentProcessExplicitAppUserModelID([MarshalAs(UnmanagedType.LPWStr)] string AppID);

        [STAThread]
        static int Main(string[] args)
        {
            try { SetCurrentProcessExplicitAppUserModelID("KinoSuite.KinoShop.Desktop.1"); } catch { }

            string root = AppDomain.CurrentDomain.BaseDirectory;
            string mainPy = Path.Combine(root, "main.py");
            if (!File.Exists(mainPy))
            {
                MessageBox.Show("Could not find main.py next to KinoShop.exe.", "KinoShop", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }

            string localApp = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string[] candidates = new string[]
            {
                Path.Combine(localApp, @"Programs\Python\Python310\pythonw.exe"),
                Path.Combine(localApp, @"Programs\Python\Python311\pythonw.exe"),
                Path.Combine(localApp, @"Programs\Python\Python312\pythonw.exe"),
                Path.Combine(localApp, @"Programs\Python\Python310\python.exe"),
                "pythonw.exe",
                "python.exe"
            };

            string pythonExe = null;
            foreach (string c in candidates)
            {
                if (c.Contains(@"\") && File.Exists(c)) { pythonExe = c; break; }
            }
            if (pythonExe == null) pythonExe = "pythonw.exe";

            string argLine = "\"" + mainPy + "\"";
            foreach (string a in args)
            {
                argLine += " \"" + a.Replace("\"", "\\\"") + "\"";
            }

            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = pythonExe;
                psi.Arguments = argLine;
                psi.WorkingDirectory = root;
                psi.UseShellExecute = false;
                psi.CreateNoWindow = true;
                Process.Start(psi);
                return 0;
            }
            catch (Exception ex)
            {
                MessageBox.Show("Failed to launch KinoShop:\n" + ex.Message, "KinoShop", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
        }
    }
}
