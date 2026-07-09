# Ezzoubir skills section preservation

Regression fixture for a source CV where `COMPÉTENCES` is visually structured across pages 3-4 and text extraction leaks experience lines plus Hellowork footers into skills.

Expected behavior:

- preserve source skill sub-sections: `Compétences fonctionnelles`, `Méthodologie de travail`, `Mainframe`, `Web .NET`, `Testeur fonctionnel`, `Base De Données`, `Compétences Organisationnelles`, `Java`
- exclude Hellowork footers: `CV créé sur`, `3 / 6`, `4 / 6`
- exclude experience sentences from skills
- avoid W hub generic re-taxonomization when source sections are clear
