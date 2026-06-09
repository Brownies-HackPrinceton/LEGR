const ORCHESTRATOR_URL = 'http://localhost:8000';
const COMPANY_ID = '00000001-0000-4000-8000-000000000001';

// Supabase Configuration
const SUPABASE_URL = 'https://hytblxitlqnrkgsaifez.supabase.co';
const SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh5dGJseGl0bHFucmtnc2FpZmV6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY0ODExNzgsImV4cCI6MjA5MjA1NzE3OH0.P2sYWRANqNlnh4imWrELjsUErzqq8ye6a1Vc85uwIxY';
const supabaseClient = supabase.createClient(SUPABASE_URL, SUPABASE_KEY);

const swipeBtn = document.getElementById('swipe-button');
const statusTray = document.getElementById('status-tray');
const statusMsg = document.getElementById('status-message');
const swipesList = document.getElementById('swipes-list');

let recentSwipes = JSON.parse(localStorage.getItem('recent_swipes') || '[]');

function updateSwipesList() {
    swipesList.innerHTML = recentSwipes.map(s => `
        <div class="swipe-pill">
            <span class="merchant">${s.merchant}</span>
            <span class="amount">$${Number(s.amount).toFixed(2)}</span>
        </div>
    `).join('');
}

updateSwipesList();

swipeBtn.addEventListener('click', async () => {
    const merchant = document.getElementById('merchant').value;
    const amount = document.getElementById('amount').value;
    const pillar = document.getElementById('pillar').value;
    const employee_id = document.getElementById('employee_id').value;
    
    // Get name from the selected employee dropdown
    const empSelect = document.getElementById('employee_id');
    const submitted_by = empSelect.options[empSelect.selectedIndex].text.split('(')[0].trim();
    
    const memo = document.getElementById('memo').value;

    if (!merchant || !amount) {
        showStatus('Please fill in Merchant and Amount.', 'error');
        return;
    }

    // Map pillar to a default category for better charts
    const categoryMap = {
        'ai_spend': 'ai_api',
        'saas_sprawl': 'saas',
        'compliance': 'meals'
    };

    const transactionId = crypto.randomUUID();
    const finalAmount = parseFloat(amount);
    const isAutoApproved = finalAmount < 100;

    const payload = {
        id: transactionId,
        company_id: COMPANY_ID,
        merchant: merchant,
        amount: finalAmount,
        pillar: pillar,
        category: categoryMap[pillar] || 'unknown',
        status: isAutoApproved ? 'resolved' : 'pending',
        submitted_by: submitted_by,
        employee_id: employee_id,
        memo: memo || null,
        created_at: new Date().toISOString()
    };

    swipeBtn.classList.add('loading');
    swipeBtn.innerText = 'PROCESSING...';
    
    try {
        // 1. Insert into Supabase directly for dashboard persistence
        const { error: sbError } = await supabaseClient
            .from('transactions')
            .insert([payload]);

        if (sbError) throw sbError;

        // 2. Call orchestrator (optional background trigger)
        const response = await fetch(`${ORCHESTRATOR_URL}/webhook/transaction`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        // Dynamic status feedback for demo
        const msg = isAutoApproved 
            ? "Card Approved! Transaction logged and synced. ✓" 
            : "Transaction Flagged! Exceeds $100 limit. ⚠";
        const type = isAutoApproved ? 'success' : 'warning';
        
        showStatus(msg, type);
        
        recentSwipes.unshift({ merchant, amount });
        recentSwipes = recentSwipes.slice(0, 5);
        localStorage.setItem('recent_swipes', JSON.stringify(recentSwipes));
        updateSwipesList();
        
    } catch (error) {
        console.error('Error swiping card:', error);
        if (error.code === '23503') {
            showStatus('F-Key Error: Employee ID not found in database.', 'error');
        } else {
            showStatus(`Error: ${error.message || 'Check terminal connection'}`, 'error');
        }
    } finally {
        swipeBtn.classList.remove('loading');
        swipeBtn.innerText = 'SWIPE CARD';
    }
});

function showStatus(text, type) {
    statusTray.className = `status-tray ${type}`;
    statusMsg.innerText = text;
    statusTray.style.display = 'block';
    
    setTimeout(() => {
        statusTray.style.display = 'none';
        statusTray.className = 'status-tray';
    }, 5000);
}
