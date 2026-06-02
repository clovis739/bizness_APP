"""Curated market intelligence context for BizSense advisory reports."""

from copy import deepcopy

DEFAULT_MARKET_CONTEXT = {
    "sector_snapshot": "Cameroonian SMEs compete in a price-sensitive market where trust, availability, mobile money convenience, and reliable delivery strongly influence customer decisions.",
    "sector_trends": [
        "Customers increasingly compare prices and quality through WhatsApp, Facebook, TikTok, and local referral groups before buying.",
        "Mobile money and fast response times are becoming basic expectations for urban and semi-urban customers.",
        "Businesses that keep simple financial records are better positioned to access supplier credit, microfinance, and grant programs.",
    ],
    "customer_behavior_trends": [
        "Buyers prefer businesses that can confirm price, stock, and delivery quickly.",
        "Repeat customers respond well to loyalty offers, bundled services, and visible proof of quality.",
    ],
    "pricing_pressure": "Price competition remains high because informal sellers can undercut formal businesses, so owners need clear differentiation and cost control.",
    "common_risks": [
        "Power instability can raise costs and reduce service reliability.",
        "Imported inputs can become expensive when exchange rates, freight costs, or border delays change.",
        "Informal competitors can pressure margins if the business competes only on price.",
    ],
    "funding_opportunities": [
        "Microfinance institutions and cooperatives for working capital once records are consistent.",
        "Municipal, NGO, and youth entrepreneurship calls when the business can show traction.",
        "Supplier credit after building a reliable purchase and payment history.",
    ],
    "recommended_growth_channels": [
        "WhatsApp Business catalog with clear prices and weekly offers.",
        "Referral partnerships with nearby complementary businesses.",
        "Customer follow-up list for repeat purchases and debt recovery.",
    ],
    "recommended_kpis": [
        {"name": "Monthly Revenue", "target": "Grow by 8-12% over the next quarter", "why_it_matters": "Shows whether demand and sales activity are improving."},
        {"name": "Gross Margin", "target": "Protect at least 25-35% margin where possible", "why_it_matters": "Prevents growth from hiding weak profitability."},
        {"name": "Repeat Customer Rate", "target": "Track returning customers every month", "why_it_matters": "Repeat demand lowers marketing cost and stabilizes cash flow."},
    ],
}

INDUSTRY_MARKET_CONTEXT = {
    "agriculture": {
        "sector_snapshot": "Agriculture demand remains strong, but margins depend on seasonality, storage, transport reliability, and access to buyers beyond the local market.",
        "sector_trends": [
            "Urban demand for fresh, traceable, and consistently supplied food products continues to rise.",
            "Small producers are using WhatsApp groups and local aggregators to reduce dependence on middlemen.",
            "Post-harvest losses create opportunities for drying, packaging, cold storage, and simple processing.",
        ],
        "customer_behavior_trends": [
            "Retailers and households increasingly value predictable supply and clear delivery schedules.",
            "Bulk buyers prefer suppliers who can document quantities, prices, and delivery history.",
        ],
        "pricing_pressure": "Prices can move quickly with season, transport cost, rainfall, and border supply, so stock planning and buyer contracts matter.",
        "common_risks": [
            "Weather shocks and pests can reduce output.",
            "Poor roads and fuel costs can reduce margin before produce reaches market.",
            "Middlemen can capture value when producers lack direct buyer relationships.",
        ],
        "recommended_growth_channels": [
            "Direct WhatsApp ordering for retailers and restaurants.",
            "Partnerships with market sellers, food vendors, and small supermarkets.",
            "Simple packaging or processing to extend shelf life and raise selling price.",
        ],
    },
    "retail": {
        "sector_snapshot": "Retail is driven by convenience, price visibility, stock availability, and customer trust. Digital ordering is becoming a strong advantage even for small shops.",
        "sector_trends": [
            "Customers expect fast price confirmation through WhatsApp before visiting or ordering.",
            "Retailers with inventory discipline avoid cash being trapped in slow-moving stock.",
            "Mobile money payments and delivery partnerships are expanding the reachable customer base.",
        ],
        "customer_behavior_trends": [
            "Customers compare prices across shops and online posts before buying.",
            "Buyers return to shops that remember preferences and offer small loyalty benefits.",
        ],
        "pricing_pressure": "Retail margins are pressured by informal sellers and imported substitutes, so stock rotation and supplier negotiation are critical.",
        "common_risks": [
            "Dead stock ties up cash and reduces ability to restock fast-moving products.",
            "Supplier price changes can quickly reduce margins.",
            "Customer debt can grow if credit sales are not tracked daily.",
        ],
        "recommended_growth_channels": [
            "WhatsApp product catalog with best sellers and weekly bundles.",
            "Neighborhood delivery or pickup for repeat customers.",
            "Cross-selling at checkout based on common customer baskets.",
        ],
    },
    "tech": {
        "sector_snapshot": "Tech-enabled SMEs can scale faster through digital distribution, but trust, support quality, pricing, and local problem fit determine adoption.",
        "sector_trends": [
            "Businesses are adopting payment, inventory, marketing, and customer management tools to reduce manual work.",
            "AI and automation interest is growing, but buyers still need clear ROI and hands-on support.",
            "Mobile-first solutions are stronger because many users rely on phones more than laptops.",
        ],
        "customer_behavior_trends": [
            "SME buyers prefer simple demos, monthly pricing, and support over complex feature lists.",
            "Customers trust products more when they see local proof, testimonials, and quick onboarding.",
        ],
        "pricing_pressure": "Global software and informal freelancers create pricing pressure, so local support and Cameroon-specific workflows should be emphasized.",
        "common_risks": [
            "Long sales cycles can strain cash flow.",
            "Weak onboarding can increase churn even when the product is useful.",
            "Poor internet reliability can reduce usage if offline workflows are not supported.",
        ],
        "recommended_growth_channels": [
            "Demo-driven sales through WhatsApp, LinkedIn, and SME communities.",
            "Partnerships with accountants, consultants, cyber cafes, and business centers.",
            "Referral programs for existing customers who bring other SMEs.",
        ],
    },
    "manufacturing": {
        "sector_snapshot": "Manufacturing growth depends on controlling input costs, power reliability, consistent quality, and access to distributors or institutional buyers.",
        "sector_trends": [
            "Local sourcing and import substitution are creating opportunities for reliable local producers.",
            "Buyers want consistent quality, packaging, and predictable delivery times.",
            "Energy efficiency is becoming a direct margin advantage for small manufacturers.",
        ],
        "customer_behavior_trends": [
            "Distributors prefer suppliers who can maintain quality and volume over time.",
            "Customers increasingly judge products by packaging, durability, and after-sales support.",
        ],
        "pricing_pressure": "Imported substitutes and informal producers pressure price, so quality, packaging, and reliability must justify the margin.",
        "common_risks": [
            "Power outages can interrupt production and increase unit cost.",
            "Input price volatility can shrink margins if pricing is not reviewed often.",
            "Quality inconsistency can quickly damage repeat orders.",
        ],
        "recommended_growth_channels": [
            "Distributor agreements with clear minimum order quantities.",
            "B2B sales to retailers, restaurants, institutions, or contractors.",
            "Quality-focused branding and packaging improvements.",
        ],
    },
    "services": {
        "sector_snapshot": "Service businesses grow through trust, referrals, responsiveness, and visible proof of results. Strong operators package services clearly instead of selling vague labor.",
        "sector_trends": [
            "Customers increasingly discover providers through social media, referrals, and WhatsApp status updates.",
            "Bundled service packages make pricing easier and reduce negotiation friction.",
            "Fast follow-up and customer reviews strongly influence repeat business.",
        ],
        "customer_behavior_trends": [
            "Customers want transparent pricing, quick booking, and proof of previous work.",
            "Repeat clients expect reminders, maintenance offers, and convenient payment options.",
        ],
        "pricing_pressure": "Informal providers often compete on low prices, so reliability, guarantees, and documented quality are important differentiators.",
        "common_risks": [
            "Overdependence on the owner limits growth.",
            "Unclear pricing can reduce margin through negotiation.",
            "Poor customer follow-up can waste referral potential.",
        ],
        "recommended_growth_channels": [
            "Before-and-after proof on WhatsApp status and Facebook pages.",
            "Referral rewards for satisfied customers.",
            "Monthly service packages for repeat clients or businesses.",
        ],
    },
}

REGION_CONTEXT = {
    "littoral": "Littoral, especially Douala, has strong purchasing power, logistics access, and dense competition. Speed, reliability, and differentiation matter.",
    "centre": "Centre, especially Yaounde, has strong demand from public workers, institutions, students, and service businesses. Trust and formal presentation matter.",
    "west": "West has active trading networks and strong SME culture. Relationship selling, distribution discipline, and cost control matter.",
    "south west": "South West businesses should plan carefully around security, logistics reliability, and customer trust while using local networks for resilience.",
    "north west": "North West businesses should prioritize resilience, trusted local partnerships, and flexible supply arrangements because disruption risk is higher.",
    "north": "Northern markets often reward essential goods, agriculture-linked services, and efficient distribution, but transport and purchasing power must be managed.",
    "far north": "Far North markets require strong cost discipline, security awareness, and practical distribution partnerships for resilient growth.",
}

BUSINESS_TYPE_CONTEXT = {
    "sole proprietorship": "As a sole proprietor, the owner should systemize sales records, customer follow-up, and daily cash tracking so the business can grow beyond personal memory.",
    "limited company": "As a limited company, the business should use stronger reporting, documented processes, and formal partnerships to access larger buyers and financing.",
    "partnership": "As a partnership, clear role separation, expense approval, and profit-sharing records are important to prevent internal friction.",
}


def _normalise_key(value):
    return str(value or "").strip().lower()


def get_market_intelligence_context(business_data):
    """Return curated market context tailored by industry, region, and business type."""
    context = deepcopy(DEFAULT_MARKET_CONTEXT)
    industry_context = INDUSTRY_MARKET_CONTEXT.get(_normalise_key(business_data.get("industry")))
    if industry_context:
        context.update(deepcopy(industry_context))

    context["regional_note"] = REGION_CONTEXT.get(
        _normalise_key(business_data.get("region")),
        "This region requires attention to purchasing power, logistics reliability, customer trust, and informal competition.",
    )
    context["business_type_note"] = BUSINESS_TYPE_CONTEXT.get(
        _normalise_key(business_data.get("business_type")),
        "The business should document sales, expenses, customer follow-up, and weekly performance so decisions are based on evidence.",
    )
    context["context_source"] = "Curated BizSense sector intelligence, personalized by AI with the user's business profile and prediction results."
    return context
