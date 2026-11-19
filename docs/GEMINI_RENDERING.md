# Gemini rendering for the existing Realistic Rendering workspace

KÜCHE7 sends the captured 3D PNG and the presentation prompt to Google's Gemini image-editing API only after the employee confirms the upload. The generated PNG is an independent presentation image; it does not change the project, BOM, quotation, nesting or engineering exports. The image may differ from the actual design.

Set the API key in the process environment before launching KÜCHE7. In PowerShell, for the current terminal session:

```powershell
$env:GEMINI_API_KEY = '<key from a secure local store>'
.venv\Scripts\python.exe -m kuchhe7
```

Open **View → Realistic Rendering**, select **Google Gemini**, capture the 3D scene, then select a style and click **Generate AI render**. Confirm the external image upload. The result appears beside the original capture and can be saved as PNG. **OpenAI** remains selectable. **Automatic / configured** preserves the existing `KUCHE7_RENDER_PROVIDER` setting; without that setting it prefers the configured custom endpoint, then OpenAI, then Gemini.

The default Gemini image-editing model is `gemini-nano-banana-2.1`. Set `KUCHE7_GEMINI_IMAGE_MODEL=gemini-3.1-flash-image` to use the other supported model. Access, charges and quotas depend on the Google account and model. The adapter uses the documented Gemini Interactions API image input and keeps provider requests off the UI thread.

Without `GEMINI_API_KEY`, Gemini generation is unavailable and ordinary 3D capture and PNG saving still work. Never put an API key in project JSON, a Git-tracked `.env` file, screenshots or logs. For a distributed commercial desktop build, use a server-side credential proxy and usage controls; a key supplied directly to a desktop process is accessible to that machine's user.

Reference: [Google Gemini image editing](https://aistudio.google.com/docs/image-generation) and [API key guidance](https://aistudio.google.com/docs/api-key).
