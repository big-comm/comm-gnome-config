<div align="center">

# 🔵 BigLinux Community GNOME Config

**The Definitive GNOME Session for BigLinux Community Edition**

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg?style=for-the-badge)](LICENSE)
[![GNOME](https://img.shields.io/badge/GNOME-4A86CF?style=for-the-badge&logo=gnome&logoColor=white)](https://gnome.org/)
[![Arch Linux](https://img.shields.io/badge/Arch_Linux-1793D1?style=for-the-badge&logo=arch-linux&logoColor=white)](https://archlinux.org/)

</div>

---

## 📖 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Project Structure](#-project-structure)
- [Key Components](#-key-components)
- [Development](#-development)
- [Contributing](#-contributing)
- [License](#-license)

---

## 📋 Overview

The **comm-gnome-config** package delivers a tailored GNOME experience for BigLinux Community users. It handles the critical "first boot" configuration, ensuring that language, keyboard, and theme settings from the live environment are flawlessly applied to the installed system.

It acts as the bridge between the BigLinux infrastructure and the vanilla GNOME desktop.

---

## 🚀 Features

- **Seamless Setup**: Automatically inherits settings (Locale, Keyboard) from the installer.
- **Visual Consistency**: Applies BigLinux themes (Adwaita/Dark) and wallpapers out of the box.
- **Hardware Optimization**:
  - Auto-selects the best GTK4 renderer (`gl` vs `cairo`).
  - Integrates **JamesDSP** for superior audio processing.
- **Keyboard Smarts**: Configures X11 and IBus layouts automatically.

---

## 📁 Project Structure

```tree
comm-gnome-config/
├── pkgbuild/                 # Arch Linux packaging files
└── usr/bin/
    └── startgnome-community  # The session bootstrap script
```

---

## 🔧 Key Components

### `startgnome-community`

This script is the heart of the configuration process. It runs immediately upon the first login to:

1.  **Environment Setup**: Defines critical variables like `GSK_RENDERER` and `XDG_CURRENT_DESKTOP`.
2.  **Localization**: Reads `/etc/big-default-config/big_language` to set the system locale.
3.  **Input Configuration**: Applies the keyboard layout chosen during installation.
4.  **Audio Setup**: Launches and configures JamesDSP if enabled.

---

## 🛠️ Development

### Building the Package

```bash
cd pkgbuild
makepkg -si
```

### Testing

You can simulate the startup process in a terminal:

```bash
# Debug run with verbose output
bash -x /usr/bin/startgnome-community
```

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/amazing-feature`).
3. Commit your changes (`git commit -m 'Add amazing feature'`).
4. Push to the branch (`git push origin feature/amazing-feature`).
5. Open a Pull Request.

---

## 📄 License

Distributed under the **GPL-3.0 License**. See [LICENSE](LICENSE) for more information.
