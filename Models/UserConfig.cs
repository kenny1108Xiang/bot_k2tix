using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Text.Json;
using kktix.Models;

namespace kktix.Models
{
    internal class UserConfig
    {
        public static UserConfig Instance { get; private set; } = new();

        public static void Load(UserConfig config)
        {
            Instance = config;
        }

        public string Username { get; set; } = string.Empty;
        public string Password { get; set; } = string.Empty;
        public string TicketName1 { get; set; } = string.Empty;
        public string TicketName2 { get; set; } = string.Empty;
        public string TicketPrice { get; set; } = string.Empty;
        public string TicketQuantity { get; set; } = string.Empty;
        public string TicketUrl { get; set; } = string.Empty;
        public bool IsAutoAllocation { get; set; } = true; // 預設為系統選位
        public bool IsAutoPayment { get; set; }

        // 宣告 SaleTime 為 台灣台北標準時間
        public DateTimeOffset SaleTime { get; set; } =
            TimeZoneInfo.ConvertTime(DateTimeOffset.UtcNow, TimeZoneInfo.FindSystemTimeZoneById("Taipei Standard Time"));
    }
}
