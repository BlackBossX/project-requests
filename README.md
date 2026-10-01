
# <div align="center"> Project Repository Requests </div>
###  <div align="center"> Department of Statistics & Computer Science • University of Kelaniya  </div>

Welcome! This portal allows students in the Department of Statistics & Computer Science to request an official GitHub repository for their module projects.

---

## 🚀 How to Request a Repository

You do **not** need any Git knowledge or terminal commands to request a repository.

<div align="center">
  <br>
  <a href="https://github.com/SCSSA-UoK/project-requests/issues/new?template=request.yml">
    <img src="https://img.shields.io/badge/👉_CLICK_HERE_TO_REQUEST_A_REPOSITORY-2ea44f?style=for-the-badge&logo=github&logoColor=white" alt="Request Repository" width="420">
  </a>
  <br><br>
</div>

1. **Click the green button above** (or go to the **Issues** tab → **New Issue**).
2. **Fill out the short form:**
   * **Module:** Select your module from the dropdown.
   * **Academic Year:** Select the academic year for this project.
   * **Project Short Title:** A 1–4 word title with spaces or hyphens (e.g. `Library System`, `Smart-Bus`).
   * **Project Description:** A short sentence about what you are building.
   * **Team Members (Members 1–4):** For each member enter their **Student No**, **Full Name**, and **GitHub Username**. Groups of 2–4 are supported — leave unused rows blank. Member 1 is the Project Lead.
3. **Click "Submit new issue".**

Once a coordinator approves it, your private repository will be created automatically — with a **group number assigned for you**.

---

## 🏷️ How Repositories Are Named

You do **not** choose a repository name — it is generated automatically based on your module, batch, and a sequential group number:

$$\text{MODULE}-\text{YY-YY}-\text{G}\text{NN}-\text{SHORT-TITLE}$$

| Part | What it means | Example |
| :--- | :--- | :--- |
| **MODULE** | Short code for your module (uppercase) | `FSSD` |
| **YY-YY** | The academic year | `24-25`, `25-26` |
| **GNN** | Auto-assigned group number per academic year (zero-padded) | `G01`, `G12`, `G47` |
| **SHORT-TITLE** | Your 1–4 word project title (auto Title Case) | `Smart-Bus`, `Library-System` |

### ✅ Examples:
* `FSSD-24-25-G01-Library-System`
* `FSSD-24-25-G12-Smart-Bus`
* `FSSD-25-26-G47-Ecommerce-App`
  
---

## 📚 Supported Modules & Academic Years

| Module Code | Full Name |
| :--- | :--- |
| `FSSD` | COSC 32133 / BECS 32263 – Full-Stack Software Development |

| Academic Year | Code |
| :--- | :--- |
| `24/25` | `24-25` |
| `25/26` | `25-26` |

---

## 👥 What Happens After Approval?

* **Group Number:** Your team is automatically assigned the next available group number.
* **Project Lead:** Member 1 (the student who submitted the request) becomes the **Admin** of the new repository.
* **Teammates:** Members 2–4 will receive an **invitation email** from GitHub granting them write (`push`) access.
* **Privacy:** All repositories are created **Private** by default so your code stays safe and secure.
* **Project Registry:** Your group details (Student Nos, names, GitHub usernames, repo link, and title) are automatically recorded in the project registry CSV.

---

## 📋 Project Registry

Every approved request is automatically logged to `projects.csv` in the private documentation repository (`SCSSA-UoK/scssa-project-records`). This file is the single source of truth for all provisioned groups.

| Column | Description |
| :--- | :--- |
| **Group No** | Auto-assigned group number (e.g. `G01`) |
| **Repo Name** | Full repository name |
| **Repo Link** | Direct GitHub URL to the repository |
| **Project Title** | Short title as submitted |
| **Module** | Module code (`FSSD`) |
| **Academic Year** | Academic year (`24-25`, `25-26`) |
| **Member1–4 Student No** | University student numbers |
| **Member1–4 Name** | Full names |
| **Member1–4 GitHub** | GitHub usernames |

### 📥 Downloading the Excel Report

After every approval, a formatted Excel (`.xlsx`) report is generated and committed directly to the private documentation repository.

1. Go to the `SCSSA-UoK/scssa-project-records` repository (requires Admin access).
2. Download the `projects.xlsx` file directly from the repository.

The Excel file includes navy-styled headers, alternating row colours, auto-filter dropdowns, a frozen header row, and clickable repository hyperlinks.

---

## ❓ Frequently Asked Questions

**1. Where do my teammates accept the invite?**  
They will receive an email from GitHub, or they can visit [github.com/notifications](https://github.com/notifications) to accept.

**2. Can I add more members or lecturers later?**  
Yes! As the repository Admin, you can go to **Settings → Collaborators** inside your new project repository at any time.

**3. What if I make a mistake in my request?**  
The bot will leave a friendly comment telling you what to fix. Just click the **Edit** button on your issue, fix it, and the bot will re-check it automatically.

**4. How is my group number decided?**  
Group numbers are assigned automatically and sequentially when your request is approved — no action needed from you.

**5. What format should my Student No be in?**  
Enter it exactly as shown on your student ID (e.g. `EC/2022/001`). The bot does not validate the format, so please double-check before submitting.

**6. Can groups have fewer than 4 members?**  
Yes — groups of **2, 3, or 4** members are all supported. Simply leave the unused Member rows blank.

**7. How do I get the Excel project report?**  
It is automatically saved in the private `scssa-project-records` repository. Administrators can download it from there at any time.

---

## 📞 Department Contact

**Department of Statistics & Computer Science**  
Faculty of Science, University of Kelaniya  
Dalugama, Kelaniya, Sri Lanka  

* **Email:** [dscs@kln.ac.lk](mailto:dscs@kln.ac.lk)  
* **Phone:** +94 (0)11 2908780 / +94 (0)11 2903371  
* **Office Hours:** Monday – Friday (8:00 AM – 4:00 PM)  
