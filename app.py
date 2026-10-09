import math
import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text

app = Flask(__name__)
app.config['SECRET_KEY'] = 'hackathon-secret-key-123'
# Use simple SQLite database in the local directory
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///farmdirect.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Models ---

class Produce(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    farmer_name = db.Column(db.String(100), nullable=False)
    produce_type = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    quality = db.Column(db.String(50), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=True) # Indicative price
    
class Requirement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    buyer_name = db.Column(db.String(100), nullable=False)
    produce_type = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    location = db.Column(db.String(100), nullable=False)
    quality = db.Column(db.String(50), nullable=False)

SIMULATED_STATUSES = ("Order Placed", "Pickup Scheduled", "In Transit", "Delivered")

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    buyer_name = db.Column(db.String(100), nullable=False)
    farmer_name = db.Column(db.String(100), nullable=False)
    produce_type = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    farmer_location = db.Column(db.String(100), nullable=False, default="Not provided")
    buyer_location = db.Column(db.String(100), nullable=False, default="Not provided")
    status = db.Column(db.String(50), default=SIMULATED_STATUSES[0])


SUPPORTED_CROPS = ("Wheat", "Rice", "Chana", "Tur Dal", "Moong", "Soybean")
DEMO_BASELINES = {
    "Wheat": {"demand_kg": 900, "price_per_kg": 25.0},
    "Rice": {"demand_kg": 1200, "price_per_kg": 38.0},
    "Chana": {"demand_kg": 650, "price_per_kg": 70.0},
    "Tur Dal": {"demand_kg": 500, "price_per_kg": 115.0},
    "Moong": {"demand_kg": 550, "price_per_kg": 95.0},
    "Soybean": {"demand_kg": 700, "price_per_kg": 45.0},
}


def round_up_quantity(quantity):
    return int(math.ceil(quantity / 50) * 50)


def build_demand_forecasts(produces, requirements):
    forecasts = {}
    for crop in SUPPORTED_CROPS:
        available_kg = sum(max(p.quantity, 0) for p in produces if p.produce_type == crop)
        crop_requirements = [r for r in requirements if r.produce_type == crop and r.quantity > 0]
        if crop_requirements:
            observed_demand = sum(r.quantity for r in crop_requirements)
            source = "Saved buyer requirements"
            explanation = (
                f"{observed_demand} kg requested across {len(crop_requirements)} saved requirement(s); "
                f"{available_kg} kg currently listed."
            )
        else:
            observed_demand = DEMO_BASELINES[crop]["demand_kg"]
            source = "Sample/demo demand baseline"
            explanation = (
                f"No saved buyer requirements; using the {observed_demand} kg demo baseline "
                f"and checking against {available_kg} kg currently listed."
            )

        if available_kg == 0 or observed_demand >= available_kg:
            level = "High"
        elif observed_demand >= available_kg * 0.5:
            level = "Medium"
        else:
            level = "Low"

        forecasts[crop] = {
            "level": level,
            "estimated_kg": round_up_quantity(observed_demand * 1.1),
            "available_kg": available_kg,
            "source": source,
            "explanation": explanation,
        }
    return forecasts


def build_price_estimates(produces):
    estimates = {}
    for crop in SUPPORTED_CROPS:
        listing_prices = [
            p.price for p in produces
            if p.produce_type == crop and p.price is not None and p.price > 0
        ]
        if listing_prices:
            price = round(sum(listing_prices) / len(listing_prices), 2)
            source = f"Average of {len(listing_prices)} saved farmer listing price(s)."
        else:
            price = DEMO_BASELINES[crop]["price_per_kg"]
            source = "Sample/demo baseline; no saved farmer listing price for this crop."
        estimates[crop] = {"price_per_kg": price, "source": source}
    return estimates


def score_match(produce, requirement):
    if produce.produce_type != requirement.produce_type or produce.quantity <= 0 or requirement.quantity <= 0:
        return None

    reasons = ["Produce type matches."]
    quantity_covered = min(produce.quantity, requirement.quantity)
    quantity_score = round(25 * quantity_covered / requirement.quantity)
    if produce.quantity >= requirement.quantity:
        reasons.append("Available quantity can cover the full request.")
    else:
        reasons.append(f"Partial quantity match: {quantity_covered} kg of the request can be met.")

    quality_rank = {"Standard": 1, "Medium": 2, "High": 3}
    quality_gap = abs(quality_rank.get(produce.quality, 1) - quality_rank.get(requirement.quality, 1))
    quality_score = 25 if quality_gap == 0 else 17 if quality_gap == 1 else 10
    reasons.append(
        "Quality matches."
        if quality_gap == 0
        else "Quality differs; confirm it with the other party."
    )

    same_location = produce.location.strip().casefold() == requirement.location.strip().casefold()
    location_score = 20 if same_location else 8
    reasons.append(
        "Farmer and buyer locations match."
        if same_location
        else "Locations differ; confirm whether the trade works for both parties."
    )

    score = 30 + quantity_score + quality_score + location_score
    label = "Good" if score >= 80 else "Fair" if score >= 60 else "Limited"
    return {
        "score": score,
        "label": label,
        "reasons": reasons,
        "order_quantity": quantity_covered,
    }


def build_buyer_matches(produces, requirements):
    matches = []
    for requirement in requirements:
        for produce in produces:
            score = score_match(produce, requirement)
            if score:
                matches.append({"requirement": requirement, "produce": produce, **score})
    return sorted(matches, key=lambda match: match["score"], reverse=True)


def build_listing_recommendations(produces, requirements, forecasts, price_estimates):
    recommendations = {}
    for produce in produces:
        if produce.quantity <= 0:
            continue
        forecast = forecasts[produce.produce_type]
        price = price_estimates[produce.produce_type]["price_per_kg"]
        possible_matches = [
            (requirement, score_match(produce, requirement))
            for requirement in requirements
            if requirement.produce_type == produce.produce_type
        ]
        possible_matches = [(requirement, score) for requirement, score in possible_matches if score]
        best_match = max(
            possible_matches,
            key=lambda item: (item[1]["order_quantity"] * item[1]["score"], item[1]["score"]),
            default=None,
        )

        if best_match and best_match[1]["order_quantity"] >= produce.quantity:
            action = "Sell"
            reason = "A suitable buyer requirement can cover this full listing."
        elif best_match:
            action = "Split"
            matched_quantity = best_match[1]["order_quantity"]
            reason = (
                f"A buyer requirement can match {matched_quantity} kg; consider splitting "
                f"the remaining {produce.quantity - matched_quantity} kg."
            )
        elif forecast["level"] == "High":
            action = "Sell"
            reason = "High estimated demand; no saved direct buyer match was found."
        elif forecast["level"] == "Medium":
            action = "Split"
            reason = "Moderate estimated demand; consider selling part and retaining the rest."
        else:
            action = "Store"
            reason = "Lower estimated demand and no saved buyer match; consider holding this listing."

        if best_match:
            reason += f" Best match: {best_match[0].buyer_name} ({best_match[1]['label']}, {best_match[1]['score']}%)."
        reason += f" Demand: {forecast['level']} ({forecast['estimated_kg']} kg estimate); indicative demo estimate ₹{price:.2f}/kg."
        recommendations[produce.id] = {"action": action, "reason": reason}
    return recommendations


def estimate_simulated_logistics(order):
    farmer_location = (order.farmer_location or "").strip()
    buyer_location = (order.buyer_location or "").strip()
    has_locations = bool(farmer_location) and buyer_location.casefold() != "not provided"
    if has_locations:
        locations = sorted((farmer_location.casefold(), buyer_location.casefold()))
        location_text = "|".join(locations)
        seed = sum((index + 1) * ord(character) for index, character in enumerate(location_text))
        note = "Deterministic demo estimate from the location names only; no map or route lookup."
    else:
        seed = order.id * 37
        note = "Generic simulated placeholder because a location is missing; not based on a route."

    distance_km = 35 + seed % 216
    if distance_km <= 100:
        delivery_window = "1-2 days"
    elif distance_km <= 180:
        delivery_window = "2-4 days"
    else:
        delivery_window = "4-6 days"
    return {
        "distance": f"~{distance_km} km",
        "delivery_window": delivery_window,
        "note": note,
    }


def migrate_order_logistics_schema():
    inspector = inspect(db.engine)
    if not inspector.has_table(Order.__tablename__):
        return

    columns = {column["name"] for column in inspector.get_columns(Order.__tablename__)}
    for column in ("farmer_location", "buyer_location"):
        if column not in columns:
            db.session.execute(text(
                f'ALTER TABLE "order" ADD COLUMN {column} VARCHAR(100) NOT NULL DEFAULT \'Not provided\''
            ))
    db.session.commit()

    if "farmer_location" not in columns or "buyer_location" not in columns:
        requirements = Requirement.query.order_by(Requirement.id.desc()).all()
        for order in Order.query.filter_by(buyer_location="Not provided").all():
            matching_locations = {
                requirement.location
                for requirement in requirements
                if requirement.buyer_name.casefold() == order.buyer_name.casefold()
                and requirement.produce_type == order.produce_type
            }
            if len(matching_locations) == 1:
                order.buyer_location = matching_locations.pop()

        for order in Order.query.filter_by(farmer_location="Not provided").all():
            matching_locations = {
                produce.location
                for produce in Produce.query.filter_by(
                farmer_name=order.farmer_name,
                produce_type=order.produce_type,
                ).all()
            }
            if len(matching_locations) == 1:
                order.farmer_location = matching_locations.pop()
        db.session.commit()

    Order.query.filter_by(status="Placed").update(
        {Order.status: SIMULATED_STATUSES[0]}, synchronize_session=False
    )
    db.session.commit()

# --- Database Initialization ---
def init_db():
    with app.app_context():
        db.create_all()
        migrate_order_logistics_schema()
        # Add sample data if database is completely empty (for hackathon demo)
        if Produce.query.count() == 0:
            p1 = Produce(farmer_name="Rajesh Patil", produce_type="Wheat", quantity=1000, quality="High", location="Nashik", price=25.0)
            p2 = Produce(farmer_name="Amit Sharma", produce_type="Soybean", quantity=500, quality="Medium", location="Pune", price=45.0)
            db.session.add_all([p1, p2])
            db.session.commit()
            
        if Requirement.query.count() == 0:
            r1 = Requirement(buyer_name="ABC Foods", produce_type="Wheat", quantity=800, location="Mumbai", quality="High")
            r2 = Requirement(buyer_name="FreshGrain Retail", produce_type="Soybean", quantity=200, location="Pune", quality="Medium")
            db.session.add_all([r1, r2])
            db.session.commit()

# --- Routes ---

@app.route('/')
def welcome():
    return render_template('welcome.html')

@app.route('/home')
def index():
    featured_produces = Produce.query.filter(Produce.quantity > 0).limit(3).all()
    return render_template('index.html', produces=featured_produces)

@app.route('/farmer', methods=['GET', 'POST'])
def farmer():
    if request.method == 'POST':
        farmer_name = request.form.get('farmer_name')
        produce_type = request.form.get('produce_type')
        quantity = int(request.form.get('quantity'))
        quality = request.form.get('quality')
        location = request.form.get('location')
        price_val = request.form.get('price')
        
        price = float(price_val) if price_val else 0.0
        
        new_produce = Produce(
            farmer_name=farmer_name,
            produce_type=produce_type,
            quantity=quantity,
            quality=quality,
            location=location,
            price=price
        )
        db.session.add(new_produce)
        db.session.commit()
        flash('Produce listed successfully!', 'success')
        return redirect(url_for('farmer'))
        
    produces = Produce.query.all()
    requirements = Requirement.query.all()
    total_produce = len(produces)
    available_qty = sum(p.quantity for p in produces)
    active_orders = Order.query.count() # simplistic metric for demo
    demand_forecasts = build_demand_forecasts(produces, requirements)
    price_estimates = build_price_estimates(produces)
    recommendations = build_listing_recommendations(
        produces, requirements, demand_forecasts, price_estimates
    )
    
    return render_template('farmer.html', 
                           produces=produces, 
                           total_produce=total_produce, 
                           available_qty=available_qty, 
                           active_orders=active_orders,
                           supported_crops=SUPPORTED_CROPS,
                           demand_forecasts=demand_forecasts,
                           price_estimates=price_estimates,
                           recommendations=recommendations)

@app.route('/buyer', methods=['GET', 'POST'])
def buyer():
    if request.method == 'POST':
        new_req = Requirement(
            buyer_name=request.form.get('buyer_name'),
            produce_type=request.form.get('produce_type'),
            quantity=int(request.form.get('quantity')),
            location=request.form.get('location'),
            quality=request.form.get('quality')
        )
        db.session.add(new_req)
        db.session.commit()
        flash('Requirement posted successfully!', 'success')
        return redirect(url_for('buyer'))
        
    requirements = Requirement.query.all()
    
    produces = Produce.query.filter(Produce.quantity > 0).all()
    matches = build_buyer_matches(produces, requirements)
            
    return render_template('buyer.html', requirements=requirements, matches=matches)

@app.route('/marketplace', methods=['GET', 'POST'])
def marketplace():
    if request.method == 'POST':
        produce_id = int(request.form.get('produce_id'))
        order_qty = int(request.form.get('order_quantity'))
        buyer_name = request.form.get('buyer_name')
        
        produce = Produce.query.get(produce_id)
        if produce and produce.quantity >= order_qty:
            produce.quantity -= order_qty
            buyer_location = (request.form.get('buyer_location') or '').strip()
            if not buyer_location:
                matching_requirement = next(
                    (
                        requirement for requirement in Requirement.query.order_by(Requirement.id.desc()).all()
                        if requirement.buyer_name.casefold() == buyer_name.strip().casefold()
                        and requirement.produce_type == produce.produce_type
                    ),
                    None,
                )
                buyer_location = matching_requirement.location if matching_requirement else "Not provided"
            
            new_order = Order(
                buyer_name=buyer_name,
                farmer_name=produce.farmer_name,
                produce_type=produce.produce_type,
                quantity=order_qty,
                farmer_location=produce.location,
                buyer_location=buyer_location,
                status=SIMULATED_STATUSES[0],
            )
            db.session.add(new_order)
            db.session.commit()
            flash('Order placed successfully!', 'success')
        else:
            flash('Failed to place order. Invalid quantity requested.', 'error')
        return redirect(url_for('marketplace'))

    produces = Produce.query.filter(Produce.quantity > 0).all()
    return render_template('marketplace.html', produces=produces)

@app.route('/orders')
def orders():
    orders_list = Order.query.order_by(Order.id.desc()).all()
    logistics = {}
    for order in orders_list:
        logistics[order.id] = estimate_simulated_logistics(order)
    return render_template(
        'orders.html',
        orders=orders_list,
        logistics=logistics,
        simulated_statuses=SIMULATED_STATUSES,
    )


@app.route('/orders/<int:order_id>/advance', methods=['POST'])
def advance_order_status(order_id):
    order = db.session.get(Order, order_id)
    if order is None:
        flash('Order not found.', 'error')
        return redirect(url_for('orders'))

    try:
        current_index = SIMULATED_STATUSES.index(order.status)
    except ValueError:
        current_index = 0
    if current_index < len(SIMULATED_STATUSES) - 1:
        order.status = SIMULATED_STATUSES[current_index + 1]
        db.session.commit()
        flash(f'Order #{order.id} demo status updated to {order.status}.', 'success')
    else:
        flash(f'Order #{order.id} is already marked delivered in the demo flow.', 'success')
    return redirect(url_for('orders'))

if __name__ == '__main__':
    # Initialize database when running locally
    init_db()
    app.run(debug=True, port=5000)
