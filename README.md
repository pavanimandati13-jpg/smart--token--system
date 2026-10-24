# Smart Queue Token System

A web-based queue management application designed to simplify customer flow, generate service tokens, prioritize customers, and provide estimated waiting times.

## Live Demo

🚀 **Live Website:** [Smart Queue Token System](https://smart-token-system-6uua.onrender.com)

📂 **GitHub Repository:** [View Source Code](https://github.com/pavanimandati13-jpg/smart--token--system)

## Project Overview

The Smart Queue Token System helps organizations manage customer queues in a structured and efficient way. Customers can generate tokens based on their required service, while staff can manage tokens and counters. The system also provides a display board and statistics to help monitor queue activity.

## Key Features

- **Token Generation:** Generate a unique token for a customer.
- **Multiple Services:** Supports General Enquiry, Billing & Payments, Documents, and Customer Support.
- **Priority-Based Queue:** Supports normal and priority customers, including senior citizens, differently abled customers, and emergency cases.
- **Waiting-Time Estimation:** Provides estimated waiting times for customers.
- **Staff Management:** Supports staff-side token and queue management.
- **Counter Display:** Helps staff manage service counters.
- **Live Display Board:** Provides a view of queue information.
- **Statistics Dashboard:** Displays queue-related statistics.

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Application logic and backend |
| HTML | Web page structure |
| CSS | User interface styling |
| JavaScript | Client-side interactions |
| Python HTTP Server | Handles HTTP requests |
| Git and GitHub | Version control and source code hosting |
| Render | Cloud deployment and hosting |

## Application Modules

1. **Get Token** – Enter customer details and select a service and priority.
2. **Token Management** – Manage tokens and queue status.
3. **Staff Panel** – Support queue handling by staff.
4. **Counter Display** – Display counter-related information.
5. **Queue Board** – View queue information.
6. **Statistics** – Monitor queue activity.

## Getting Started

### Prerequisites

- Python 3.8 or later
- Git
- Visual Studio Code (recommended)

### Installation

**1. Clone the repository**

```bash
git clone https://github.com/pavanimandati13-jpg/smart--token--system.git
```

**2. Navigate to the project folder**

```bash
cd smart--token--system
```

**3. Run the application**

```bash
python app.py
```

If the application supports the default configuration, open the local address displayed in the terminal. The default address is commonly `http://localhost:8000`.

## How to Use

1. Open the application.
2. Navigate to **Get Token**.
3. Enter the customer's name and optional phone number.
4. Select the required service.
5. Choose the appropriate priority.
6. Generate the token.
7. Use the available staff, counter, board, and statistics sections to manage and monitor the queue.

## Project Structure

```text
smart--token--system/
├── app.py
├── static/
├── tests/
├── .vscode/
├── requirements.txt
├── README.md
└── queue.db
```

## Deployment

The application is deployed on Render and can be accessed publicly:

**Live URL:** https://smart-token-system-6uua.onrender.com

## Benefits

- Reduces confusion in customer queues.
- Organizes service requests.
- Supports priority-based service.
- Improves queue visibility for staff and customers.
- Provides a centralized
