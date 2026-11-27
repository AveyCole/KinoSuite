using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;

class KinoDrawLauncher
{
    [STAThread]
    static int Main(string[] args)
    {
        string appDir = AppDomain.CurrentDomain.BaseDirectory;
        string mainPy = Path.Combine(appDir, "main.py");
        if (!File.Exists(mainPy))
        {
            MessageBox.Show("Could not find main.py next to KinoDraw.exe:\n" + mainPy,
                "KinoDraw — KinoSuite", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }

        string pythonw = FindPythonW();
        if (string.IsNullOrEmpty(pythonw))
        {
            MessageBox.Show("Could not locate Python 3.10+ (pythonw.exe).\nPlease run run.ps1 or install Python 3.10+.",
                "KinoDraw — KinoSuite", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }

        var sb = new StringBuilder();
        sb.Append("\"").Append(mainPy).Append("\"");
        foreach (string a in args)
        {
            sb.Append(" \"").Append(a.Replace("\"", "\\\"")).Append("\"");
        }

        var psi = new ProcessStartInfo
        {
            FileName = pythonw,
            Arguments = sb.ToString(),
            WorkingDirectory = appDir,
            UseShellExecute = false,
            CreateNoWindow = true
        };

        try
        {
            Process.Start(psi);
            return 0;
        }
        catch (Exception ex)
        {
            MessageBox.Show("Failed to launch KinoDraw:\n" + ex.Message,
                "KinoDraw — KinoSuite", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    static string FindPythonW()
    {
        string localApp = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string[] candidates = new string[]
        {
            Path.Combine(localApp, @"Programs\Python\Python310\pythonw.exe"),
            Path.Combine(localApp, @"Programs\Python\Python311\pythonw.exe"),
            Path.Combine(localApp, @"Programs\Python\Python312\pythonw.exe"),
            Path.Combine(localApp, @"Programs\Python\Python313\pythonw.exe"),
            @"C:\Python310\pythonw.exe",
            @"C:\Python311\pythonw.exe",
            @"C:\Python312\pythonw.exe"
        };
        foreach (string c in candidates)
        {
            if (File.Exists(c)) return c;
        }
        return null;
    }
}
