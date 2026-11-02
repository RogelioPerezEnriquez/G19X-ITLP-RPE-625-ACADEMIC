# Ensayo de instalación desde cero

Como parte del proceso de calidad, se realizó una instalación limpia del proyecto en una computadora diferente (Windows) para validar que el `README.md` es reproducible.

## Problemas encontrados y resueltos
Durante el ensayo se encontraron los siguientes problemas, los cuales fueron documentados y corregidos en el `README.md`:
1. **Python no reconocido:** No estaba instalado o no se había marcado la casilla "Add python.exe to PATH".
2. **Node.js versión antigua:** La versión instalada no era compatible con Vite (requiere 20.19+ o 22.12+).
3. **PowerShell bloquea npm:** Windows bloquea la ejecución de `npm.ps1` por defecto. Se documentó el uso de `Set-ExecutionPolicy` o cambiar a CMD.
4. **Error de rolldown:** Un bug de `npm` con dependencias nativas. Se documentó el borrado de `node_modules` y `package-lock.json` para forzar la reinstalación.

Gracias a este ensayo, la sección "Si algo no funciona" del README incluye la solución a estos cuatro problemas comunes.
