# Web-based Task Manager Application
#### Video Demo: <>

#### Description:
This project is a web-based task manager application built using Python, Flask, SQLite, Jinja, HTML, and CSS. This application aims to provide users with a convenient way to manage their tasks, helping them stay organized and productive.

## Features:
- **User Authentication:** Users can create an account and log in to access their personalized to-do lists. This feature ensures that each user's tasks are kept private and secure.

- **Task Management:** Users can create, delete, and mark tasks as completed. The application allows users to easily add new jobs, remove tasks they no longer need, and keep track of completed tasks.

- **User-Friendly Interface:** The user interface is designed to be intuitive and user-friendly. Users can easily navigate the application, view their tasks, and make changes as needed.

## Project Structure:
- **app.py:** This is the main Python file that contains the Flask application and routes for handling user authentication and task management.

- **templates:** This directory contains HTML templates to render the web pages. Templates are organized to provide a clean and responsive user interface.

- **task.db:** SQLite database file used to store user account information and task data. Each user has a unique account with their tasks stored in this database.

## Design Choices:
- **Flask:** We chose Flask as the web framework due to its simplicity and flexibility. It allows us to build web applications quickly while maintaining code organization.It is also the preferred language of choice taught in cs50.

- **SQLite:** SQLite is used as the database system because of its lightweight nature and simplicity for small to medium-sized applications like this one.

- **Jinja:** We use Jinja templating to dynamically generate HTML content, making displaying user-specific data easier and maintaining a consistent layout.


Feel free to explore the code files for more details on the implementation. We hope you find this task manager helpful in staying organized and managing your tasks effectively!
