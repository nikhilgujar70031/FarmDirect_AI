# FarmDirect AI (Stage 3 Demo)

FarmDirect AI directly connects farmers and buyers for grains and pulses, reducing reliance on intermediaries.

This project is built with Python, Flask, HTML, CSS, and SQLite (no JavaScript).

## Project Structure
- `app.py`: Main Flask application with routing and SQLAlchemy database models.
- `requirements.txt`: Python dependencies.
- `farmdirect.db`: SQLite database (auto-generated when you run the app).
- `templates/`: HTML templates (Jinja).
- `static/`: CSS styling.

## Features Implemented
1. **Landing Page**: Explains the farmer-to-buyer flow.
2. **Farmer Dashboard**: Add new produce listings and view existing inventory.
3. **Buyer Dashboard**: Post requirements and view matching produce.
4. **Marketplace**: Browse all available farmer listings and place orders.
5. **Rule-Based Buyer Matching**: Scores crop, quantity coverage, quality, and exact location; this is not AI.
6. **Orders**: Track placed orders.
7. **Farm Insights**: Demo demand estimates, indicative prices, and Sell / Store / Split suggestions for six supported crops.
8. **Simulated Logistics**: Order shipment summaries, demo distance and delivery windows, and a persisted four-step status flow.

## Stage 2 Estimate Rules

- Demand uses saved buyer requirements and currently listed quantities when available. Missing crop requirements use clearly labeled sample/demo baselines; displayed demand is a rounded 10% planning estimate.
- Indicative price uses the average saved farmer listing price for that crop. If none is available, a sample/demo baseline is shown instead.
- Every displayed insight price is labeled **Indicative demo estimate**. These values are not live market prices, guaranteed selling prices, or professional financial advice.
- Farmer suggestions use the demand level, listing quantity, and best saved buyer match. They are demo suggestions only; farmers should make their own decisions.
- Buyer match scores are transparent rules, not an AI model. Quantity, quality, and location differences appear in each match explanation.
- Logistics distance, delivery window, and status tracking are simulated demo values only. Distances do not use maps or real routes, and no transport is booked.
- Existing order rows are retained when the app adds order location fields. Locations are filled from matching saved listings/requirements when possible; otherwise they remain marked **Not provided** and use a generic simulated distance/window placeholder that is not route-based.

## Setup & Run Instructions

1. Ensure you have Python installed.
2. Open a terminal in the project root directory (`FarmDirect`).
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the application:
   ```bash
   python app.py
   ```
5. Open your browser and go to: **http://127.0.0.1:5000**

*Note: The database and sample data are automatically initialized on the first run. Existing databases are upgraded in place to add shipment locations.*

## Demo Walkthrough

1. Open the welcome page and use its down arrow to enter FarmDirect, or go directly to **http://127.0.0.1:5000**.
2. Visit **Farmer Dashboard** to review the six crop insights and listing suggestions. Visit **Buyer Dashboard** to review rule-based match reasons.
3. Open **Marketplace**, enter a buyer name and location, choose an available quantity, and place a demo order. A matched buyer order carries the saved requirement location automatically.
4. Open **Orders** to review the shipment summary. Use **Advance to...** to move through Order Placed, Pickup Scheduled, In Transit, and Delivered; the saved status remains after refresh.
5. Use the browser's normal print command on **Orders** to print the shipment summaries without navigation or status controls.

All forecasts, indicative prices, matches, distances, delivery windows, and status tracking are simulated estimates for demonstration. They are not live prices, real AI predictions, route calculations, or transport bookings.
