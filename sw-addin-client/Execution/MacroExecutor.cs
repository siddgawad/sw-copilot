using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security;
using System.Text;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using SolidWorks.Interop.sldworks;

namespace SwCopilotAddin.Execution
{
    /// <summary>
    /// Compiles a C# source string at runtime using Roslyn, then invokes its
    /// <c>public static void Run(ISldWorks swApp)</c> entry point against the live
    /// SolidWorks instance.
    ///
    /// Threading contract: <see cref="Execute"/> must be called on the STA thread
    /// that owns the ISldWorks COM proxy (the WPF Dispatcher thread).  Dispatching
    /// to a new STA thread would require COM marshalling through the message pump;
    /// if the calling thread is simultaneously blocked in a Join() the pump stalls
    /// and you deadlock.  Long-running macros should use SolidWorks's own progress
    /// bar APIs rather than background threads.
    ///
    /// Security note: generated code runs in-process with full CLR trust.
    /// AppDomain isolation or partial-trust CAS should be evaluated before
    /// exposing this to untrusted macro sources.
    /// </summary>
    public sealed class MacroExecutor
    {
        private readonly ISldWorks _swApp;
        private static bool _assemblyResolverInstalled;

        // .NET Framework 4.8 assemblies that may not be loaded yet but are
        // commonly imported by SolidWorks macro scripts.
        private static readonly string[] CoreFrameworkDlls =
        {
            "mscorlib.dll",
            "System.dll",
            "System.Core.dll",
            "System.Runtime.dll",
            "System.Collections.dll",
            "System.Linq.dll",
            "System.Runtime.InteropServices.dll",
        };

        // Default using-directives injected when wrapping a bare method body.
        private static readonly string ScaffoldUsings = string.Join(System.Environment.NewLine,
            "using System;",
            "using System.Collections.Generic;",
            "using System.Linq;",
            "using System.Runtime.InteropServices;",
            "using SolidWorks.Interop.sldworks;",
            "using SolidWorks.Interop.swconst;",
            "using SolidWorks.Interop.swpublished;");

        public MacroExecutor(ISldWorks swApp)
        {
            InstallAssemblyResolver();
            _swApp = swApp;
        }

        // ── Public entry point ────────────────────────────────────────────────

        /// <summary>
        /// Compiles <paramref name="csharpCode"/> and invokes it.
        /// Returns a short human-readable status string for the chat panel.
        /// </summary>
        public string Execute(string csharpCode)
        {
            try
            {
                if (string.IsNullOrWhiteSpace(csharpCode))
                    return "Error: received empty macro string from backend.";

                string source = NormalizeSource(csharpCode);
                var syntaxTree = CSharpSyntaxTree.ParseText(source);

                AssertNoForbiddenIdentifiers(syntaxTree);

                var (assembly, compileErrors) = Compile(syntaxTree);
                if (assembly == null)
                    return $"Compilation failed:\n{compileErrors}";

                MethodInfo entryPoint;
                try
                {
                    entryPoint = ResolveEntryPoint(assembly);
                }
                catch (InvalidOperationException ex)
                {
                    return $"Entry-point error: {ex.Message}";
                }

                return InvokeAndCapture(entryPoint);
            }
            catch (SecurityException ex)
            {
                return $"Security blocked macro execution: {ex.Message}";
            }
            catch (Exception ex)
            {
                return FormatRuntimeError(ex);
            }
        }

        private static void InstallAssemblyResolver()
        {
            if (_assemblyResolverInstalled)
                return;

            AppDomain.CurrentDomain.AssemblyResolve += ResolveFromAddinDirectory;
            _assemblyResolverInstalled = true;
        }

        private static Assembly? ResolveFromAddinDirectory(object sender, ResolveEventArgs args)
        {
            string? addinDir = Path.GetDirectoryName(typeof(MacroExecutor).Assembly.Location);
            if (string.IsNullOrWhiteSpace(addinDir))
                return null;

            string assemblyName = new AssemblyName(args.Name).Name + ".dll";
            string candidate = Path.Combine(addinDir, assemblyName);
            if (!File.Exists(candidate))
                return null;

            return Assembly.LoadFrom(candidate);
        }

        // ── Stage 1: Source normalization ─────────────────────────────────────

        private static string NormalizeSource(string raw)
        {
            string code = raw.Trim();

            // Strip markdown fences that the LLM may accidentally include.
            code = StripMarkdownFences(code);

            // If the output contains no class declaration the LLM returned a bare
            // method body — wrap it so the compiler has a valid top-level type.
            if (!ContainsClassDeclaration(code))
                code = WrapBodyInScaffold(code);

            return code;
        }

        private static string StripMarkdownFences(string code)
        {
            if (!code.StartsWith("```", StringComparison.Ordinal))
                return code;

            int firstNewline = code.IndexOf('\n');
            int lastFence    = code.LastIndexOf("```", StringComparison.Ordinal);

            // Guard against malformed fences; let the compiler surface the error.
            if (firstNewline < 0 || lastFence <= firstNewline)
                return code;

            return code.Substring(firstNewline + 1, lastFence - firstNewline - 1).Trim();
        }

        private static bool ContainsClassDeclaration(string source)
        {
            // Use Roslyn's own parser so comments and strings don't fool us.
            var root = CSharpSyntaxTree.ParseText(source).GetRoot();
            return root.DescendantNodes().OfType<ClassDeclarationSyntax>().Any();
        }

        private static string WrapBodyInScaffold(string body)
        {
            // Indent every line of the body to sit correctly inside the method.
            string indented = string.Join(
                System.Environment.NewLine,
                body.Split(new[] { "\r\n", "\n" }, StringSplitOptions.None)
                    .Select(l => "            " + l));

            // NOTE: {{ and }} in a verbatim $-string produce literal { and }.
            // The {indented} interpolation slot is a value — its own { } chars
            // are NOT re-processed as format tokens, so C# bodies are safe here.
            return
$@"{ScaffoldUsings}

namespace SwCopilotMacro
{{
    public static class GeneratedMacro
    {{
        public static void Run(ISldWorks swApp)
        {{
{indented}
        }}
    }}
}}";
        }

        // ── Stage 2: Roslyn compilation ───────────────────────────────────────

        private static readonly HashSet<string> ForbiddenIdentifiers =
            new HashSet<string>(StringComparer.OrdinalIgnoreCase)
            {
                "Process",
                "File",
                "Directory",
                "Registry",
                "HttpClient",
                "Reflection",
                "AppDomain",
            };

        private static void AssertNoForbiddenIdentifiers(SyntaxTree syntaxTree)
        {
            var root = syntaxTree.GetRoot();
            foreach (SyntaxToken token in root.DescendantTokens())
            {
                if (!token.IsKind(SyntaxKind.IdentifierToken))
                    continue;

                string identifier = token.ValueText;
                if (!ForbiddenIdentifiers.Contains(identifier))
                    continue;

                var position = token.GetLocation().GetLineSpan().StartLinePosition;
                throw new SecurityException(
                    $"Forbidden identifier '{identifier}' at line {position.Line + 1}, column {position.Character + 1}.");
            }
        }

        private static (Assembly? assembly, string errors) Compile(SyntaxTree syntaxTree)
        {
            var options = new CSharpCompilationOptions(
                OutputKind.DynamicallyLinkedLibrary,
                optimizationLevel: OptimizationLevel.Release,
                allowUnsafe: false);

            var compilation = CSharpCompilation.Create(
                assemblyName: $"SwMacro_{Guid.NewGuid():N}",
                syntaxTrees:  new[] { syntaxTree },
                references:   GatherReferences(),
                options:      options);

            using var ms = new MemoryStream();
            var emitResult = compilation.Emit(ms);

            if (!emitResult.Success)
            {
                var sb = new StringBuilder();
                foreach (var diag in emitResult.Diagnostics.Where(d => d.Severity == DiagnosticSeverity.Error))
                {
                    var pos = diag.Location.GetLineSpan().StartLinePosition;
                    sb.AppendLine($"  [{diag.Id}] Line {pos.Line + 1}, Col {pos.Character + 1}: {diag.GetMessage()}");
                }
                return (null, sb.ToString().TrimEnd());
            }

            ms.Seek(0, SeekOrigin.Begin);
            return (Assembly.Load(ms.ToArray()), string.Empty);
        }

        private static IEnumerable<MetadataReference> GatherReferences()
        {
            var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

            // All non-dynamic assemblies loaded in this process.
            // This automatically captures every SolidWorks interop assembly the
            // host has already loaded without hard-coding paths.
            foreach (Assembly asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                if (!asm.IsDynamic && !string.IsNullOrWhiteSpace(asm.Location))
                    paths.Add(asm.Location);
            }

            // Supplement with core .NET Framework DLLs from the runtime directory
            // in case they haven't been touched by the host process yet.
            string runtimeDir = System.Runtime.InteropServices.RuntimeEnvironment
                                    .GetRuntimeDirectory();
            foreach (string dll in CoreFrameworkDlls)
            {
                string path = Path.Combine(runtimeDir, dll);
                if (File.Exists(path))
                    paths.Add(path);
            }

            string? addinDir = Path.GetDirectoryName(typeof(MacroExecutor).Assembly.Location);
            if (!string.IsNullOrWhiteSpace(addinDir) && Directory.Exists(addinDir))
            {
                foreach (string path in Directory.GetFiles(addinDir, "*.dll"))
                    paths.Add(path);
            }

            return paths.Select(path => MetadataReference.CreateFromFile(path));
        }

        // ── Stage 3: Entry-point resolution ───────────────────────────────────

        private static MethodInfo ResolveEntryPoint(Assembly assembly)
        {
            // Search every type, not just exported ones, so the scaffold's
            // internal class is found even if the LLM forgets "public".
            foreach (Type type in assembly.GetTypes())
            {
                var method = type.GetMethod(
                    name:      "Run",
                    bindingAttr: BindingFlags.Public | BindingFlags.Static,
                    binder:    null,
                    types:     new[] { typeof(ISldWorks) },
                    modifiers: null);

                if (method != null)
                    return method;
            }

            throw new InvalidOperationException(
                "Compiled assembly contains no 'public static void Run(ISldWorks)' method. " +
                "Verify the Macro Engineer system prompt enforces this exact signature.");
        }

        // ── Stage 4: Invocation and output capture ────────────────────────────

        private string InvokeAndCapture(MethodInfo runMethod)
        {
            // Temporarily redirect Console.Out so any diagnostic writes the macro
            // makes (e.g., Console.WriteLine("Extruded feature created")) are
            // surfaced in the chat panel rather than disappearing into the void.
            var originalOut = Console.Out;
            using var capture = new StringWriter();
            Console.SetOut(capture);

            try
            {
                runMethod.Invoke(null, new object[] { _swApp });

                string consoleOutput = capture.ToString().Trim();
                return string.IsNullOrEmpty(consoleOutput)
                    ? "OK — macro executed successfully."
                    : $"OK\n{consoleOutput}";
            }
            catch (TargetInvocationException tie)
            {
                // Unwrap: the real exception thrown by the macro is InnerException.
                Exception root = tie.InnerException ?? tie;
                return FormatRuntimeError(root);
            }
            catch (Exception ex)
            {
                return FormatRuntimeError(ex);
            }
            finally
            {
                Console.SetOut(originalOut);
            }
        }

        private static string FormatRuntimeError(Exception ex)
        {
            var sb = new StringBuilder();
            sb.Append($"Runtime error ({ex.GetType().Name}): {ex.Message}");

            // Surface the most-useful inner exception for COM HRESULTs.
            if (ex.InnerException != null)
                sb.Append($"\n  Caused by: {ex.InnerException.GetType().Name}: {ex.InnerException.Message}");

            return sb.ToString();
        }
    }
}
