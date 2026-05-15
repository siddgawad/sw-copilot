# SW Copilot — Quick Start for Beta Testers

## What you need

- SolidWorks 2021 (other versions may work, not tested)
- Windows 10 or 11 (64-bit)
- .NET Framework 4.8 (already on Windows 10/11)
- A free Groq API key — takes 2 minutes at [console.groq.com/keys](https://console.groq.com/keys)

---

## Step-by-step install (~10 minutes)

### 1. Get the ZIP

Download `sw-copilot-beta7.zip` and extract it to a **permanent location**:

```
C:\sw-copilot\
```

Do **not** run it from inside the ZIP file. Do **not** delete the folder after install.

### 2. Get a free Groq API key

1. Go to [console.groq.com](https://console.groq.com) and sign in (Google or GitHub)
2. Click **API Keys** → **Create API Key**
3. Copy the key (starts with `gsk_...`)

### 3. Set up the API key

Inside the folder you extracted, find:

```
C:\sw-copilot\addin\backend\SwCopilotBackend\
```

Copy the file `.env.example` and rename the copy to `.env` (no other extension).

Open `.env` in Notepad and replace:

```
GROQ_API_KEY=replace_with_your_key
```

with your actual key:

```
GROQ_API_KEY=gsk_your_actual_key_here
```

Save the file.

### 4. Install the add-in

Close SolidWorks if it is open.

Open **PowerShell as Administrator** (right-click → "Run as administrator"):

```powershell
cd C:\sw-copilot
.\Install-SwCopilot.ps1
```

You should see:
```
SW Copilot registered. Restart SolidWorks, then enable SW Copilot in Tools > Add-Ins.
```

If your SolidWorks is not in the default folder, use:

```powershell
.\Install-SwCopilot.ps1 -SolidWorksPath "C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS 2022"
```

### 5. Enable in SolidWorks

1. Start SolidWorks
2. Go to **Tools → Add-Ins**
3. Check the box next to **SW Copilot** (both checkboxes: Load + Start Up)
4. Click **OK**

A chat panel appears on the right side of SolidWorks.

---

## Try it out

Open or create a part document, then type in the chat panel:

```
create a 50mm wide 30mm deep 20mm tall box
```

The add-in will create the sketch and extrude it in the active part.

More things to try:

```
add four M6 counterbore holes at the corners
add a 2mm fillet on all edges
create a 40mm diameter shaft 100mm long
set revision to A, drawn by [your name], date today
export this as PDF
check this drawing for problems
```

---

## Troubleshooting

**"DLL not found" during install**
→ Make sure you extracted the ZIP before running Install-SwCopilot.ps1

**"SolidWorks interop DLL not found"**
→ Your SolidWorks is in a different folder. Use the `-SolidWorksPath` parameter (see Step 4)

**Chat panel does not appear**
→ Tools → Add-Ins → make sure SW Copilot is checked. Restart SolidWorks.

**"Backend not reachable" or no response**
→ The backend starts automatically when SolidWorks loads the add-in.
→ Check that `.env` has the correct Groq API key (no quotes around the key, no spaces)

**Nothing happens when I type**
→ Make sure a part document is open (File → New → Part)

---

## Uninstall

Close SolidWorks. Open PowerShell as Administrator:

```powershell
cd C:\sw-copilot
.\Uninstall-SwCopilot.ps1
```

Then delete the `C:\sw-copilot\` folder.

---

## Feedback

Report issues at: https://github.com/siddgawad/sw-copilot/issues

Built by Siddhant Gawad — mechanical engineer, CAD automation.
