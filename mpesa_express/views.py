from datetime import datetime
import requests
import base64
import re
from django.shortcuts import render
from .forms import PaymentForm
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

# M-Pesa Live API credentials and configurations
MPESA_SHORTCODE = "5483572"
MPESA_PASSKEY = "0551f00981117f05d8090a5821a8b802ed61abb16c0986b71b99a21f5df5c72d"
CONSUMER_KEY = "CMvrrAzC19NWAK7RHq6v6NAyqxAhKew5wlSGDMnCuYXUUSbU"
CONSUMER_SECRET = "zV5TM9wJfLaAlGKtMAw9lttAoBe6WanU40q1zFzauSGbSOow5oVSHSkcekGzj1gP"
MPESA_BASE_URL = "https://api.safaricom.co.ke"  # Live URL
CALLBACK_URL = "https://fec3-105-161-221-222.ngrok-free.app/mpesa/callback"  # Replace with your live callback URL

# Generate M-Pesa access token
def generate_access_token():
    try:
        credentials = f"{CONSUMER_KEY}:{CONSUMER_SECRET}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/json",
        }
        response = requests.get(
            f"{MPESA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials",
            headers=headers,
        ).json()

        if "access_token" in response:
            return response["access_token"]
        else:
            raise Exception("Access token missing in response.")

    except requests.RequestException as e:
        raise Exception(f"Failed to connect to M-Pesa: {str(e)}")

# Initiate STK Push and handle response
def initiate_push(phone, amount):
    try:
        token = generate_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        stk_password = base64.b64encode(
            (MPESA_SHORTCODE + MPESA_PASSKEY + timestamp).encode()
        ).decode()

        request_body = {
            "BusinessShortCode": MPESA_SHORTCODE,
            "Password": stk_password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": amount,
            "PartyA": phone,  # Use the phone number dynamically
            "PartyB": MPESA_SHORTCODE,
            "PhoneNumber": phone,  # Use the phone number dynamically
            "CallBackURL": CALLBACK_URL,
            "AccountReference": "account",
            "TransactionDesc": "payment for goods",
        }

        response = requests.post(
            f"{MPESA_BASE_URL}/mpesa/stkpush/v1/processrequest",
            json=request_body,
            headers=headers,
        )

        if response.status_code != 200:
            raise ValueError(f"Error: Received status code {response.status_code} from M-Pesa.")

        response_data = response.json()

        return response_data

    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return {"errorMessage": str(e)}
    except ValueError as e:
        print(f"Error in response: {e}")
        return {"errorMessage": str(e)}
    except Exception as e:
        print(f"Unexpected error: {e}")
        return {"errorMessage": "Unexpected error occurred."}

# Phone number formatting and validation
def format_phone_number(phone):
    phone = phone.replace("+", "")
    if re.match(r"^254\d{9}$", phone):
        return phone
    elif phone.startswith("0") and len(phone) == 10:
        return "254" + phone[1:]
    else:
        raise ValueError("Invalid phone number format")

# Payment view to handle the form and payment initiation
def payment_view(request):
    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            try:
                phone = format_phone_number(form.cleaned_data["phone_number"])
                amount = int(form.cleaned_data["amount"])
                response = initiate_push(phone, amount)

                # Debug: Check the type and content of the response
                print("Response received:", response)
                print("Type of response:", type(response))

                if "errorMessage" in response:
                    errorMessage = response["errorMessage"]
                    return render(request, "payment_form.html", {"form": form, "errorMessage": errorMessage})

                if response.get("ResponseCode") == "0":
                    return render(request, "pending.html")
                else:
                    errorMessage = response.get("errorMessage", "Failed to send STK push. Please try again.")
                    return render(request, "payment_form.html", {"form": form, "errorMessage": errorMessage})

            except ValueError as e:
                return render(request, "payment_form.html", {"form": form, "errorMessage": str(e)})
            except Exception as e:
                return render(request, "payment_form.html", {"form": form, "errorMessage": "An error occurred."})
    else:
        form = PaymentForm()
    return render(request, "payment_form.html", {"form": form})

# Callback handler to capture M-Pesa response
@csrf_exempt
def mpesa_callback(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
            print("M-Pesa Callback Data:", data)  # Log the callback data

            # Process the callback data here (e.g., update transaction status)
            result_code = data['Body']['stkCallback']['ResultCode']
            if result_code == 0:
                print("Payment was successful.")
                # Update transaction status in the database
            else:
                print(f"Payment failed with error code: {result_code}")
                # Handle payment failure

            return JsonResponse({"status": "success"})
        except Exception as e:
            print("Error processing callback:", e)
            return JsonResponse({"status": "error"})
